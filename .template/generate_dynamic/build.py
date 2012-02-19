import logging
from os import path
from pprint import pformat

class ConfigurationError(Exception):
	'''Indicates there is a problem with a command.'''
	pass

class Build(object):
	tasks = {}
	predicates = {}
	
	def __init__(self, config, source_dir, output_dir, external=True, remove_attribution=False, usercode=None,
			ignore_patterns=None, enabled_platforms=('chrome', 'firefox', 'safari', 'ie', 'android', 'web'),
			log=None, template_only=False, test=False, **kw):
		'''Create Forge apps, according to the supplied configuration parameters.
	
		:param config: any values which are required by the template files
		:type config: dict
		:param source_dir: directory holding the platform source
		:param output_dir: directory to which this generation process will write to
		:param external: is this a Forge build for internal debugging (i.e. un-minified for, not for customer eyes)?
		:param remove_attribution: flag to remove (built on Forge) attribution in description
		:param usercode: location of the customer's code
		:param ignore_patterns: a set of patterns that prevent certain usercode files being injected
		:param enabled_platforms: a sequence of platform names to build for
			(default: ``('chrome', 'firefox', 'safari', 'ie', 'android', 'web')``)
		:param log: a :class:`logging.Logger` instance
		:param template_only: ``True``: we just creating the platform files; ``False``
			we should also include the customer's code to create full apps
		:param test: Use the current changeset hash as the UUID
		'''
		super(Build, self).__init__()
		self.script = []
		self.log = log if log is not None else logging.getLogger(__name__)
		self.config = config
		self.source_dir = path.abspath(source_dir)
		self.output_dir = path.abspath(output_dir)
		self.external = external
		self.remove_attribution = remove_attribution
		self.usercode = usercode if usercode else path.join(self.source_dir, 'user')
		self.ignore_patterns = ignore_patterns if ignore_patterns else []
		self.log.info('enabled platforms: %s' % list(enabled_platforms))
		self.enabled_platforms = enabled_platforms
		self.template_only = template_only
		self.test = test
		self.unpackaged = {} # will hold locations of unpackaged source trees
		self.packaged = {} # will hold locations of packaged binaries
		
	def add_steps(self, steps):
		'''Append a number of steps to the script that this runner will execute
		
		:param steps: a list of 5-tuple commands
		'''
		self.script += steps
		
	def _run_task(self, func_name, args, kw):
		'run an individual task'
		if func_name == 'debug':
			import pdb
			pdb.set_trace()
			return
		if func_name not in self.tasks:
			raise ConfigurationError("{func_name} has not been registered as a task".format(func_name=func_name))
			
		args = args or ()
		kw = kw or {}
		self.log.debug('running %s(%s, %s)' % (func_name, args, kw))
		try:
			self.tasks[func_name](self, *args, **kw)
		except Exception, e:
			self.log.error('%s while running %s(%s, %s)' % (e, func_name, args, kw))
			raise
	
	def _get_predicate_functions(self, predicate_str):
		'convert a comma-separated string of predicate names to an array of functions'
		# predicate_str can be None - meaning do in any situation
		# or a comma-separated list of predicate names to invoke
		predicate_meths = []
		if predicate_str:
			for pred_name in [p.strip() for p in predicate_str.split(',')]:
				if pred_name not in self.predicates:
					raise ConfigurationError("{pred_name} has not been registered as a predicate".format(pred_name=pred_name))
				predicate_meths.append(self.predicates[pred_name])
		return predicate_meths
	
	def _preprocess_script(self, script):
		"""Pad tuples out to 5 elements and filter by predicate and platform"""
		result = []
		for raw_command in script:
			# pad incomplete command with Nones (e.g. no kw supplied)
			# 5 is expected length: platform , predicate , func_name , (args) , {kw}
			command = list(raw_command) + [None]*(5-len(raw_command))
			platform , predicate = command[:2]
			
			# "all" platform is wildcard
			# can also configure >1 platform, comma separated, e.g. android,ios
			if platform == 'all' or (set(platform.split(',')) & set(self.enabled_platforms)):
				predicate_meths = self._get_predicate_functions(predicate)
				if all(pred(self) for pred in predicate_meths):
					result.append(tuple(command))
		return result
		
	def run(self):
		'''Processes a declarative-ish script, describing a set of commands'''
		self.log.info('{0} running...'.format(self))
		self.log.info('reading app code from %s' % self.source_dir)
		self.log.info('writing new app to %s' % self.output_dir)
		
		self.script = self._preprocess_script(self.script)
		self.log.debug('{0} script:\n{1}'.format(self, pformat(self.script)))
		
		for command in self.script:
			func_name , args , kw = command[2:]
			self._run_task(func_name, args, kw)
			
		self.log.info('{0} has finished'.format(self))
	
	def __repr__(self):
		return '<Build ({0})>'.format(", ".join(self.enabled_platforms))

import codecs
import glob
import os
from os import path
import shutil
import uuid

import utils
from build import ConfigurationError
from lib import task, walk_with_depth

@task
def rename_files(build, **kw):
	if 'from' not in kw or 'to' not in kw:
		raise ConfigurationError('rename_files requires "from" and "to" keyword arguments')

	return _rename_or_copy_files(build, kw['from'], kw['to'], rename=True)

@task
def copy_files(build, **kw):
	if 'from' not in kw or 'to' not in kw:
		raise ConfigurationError('copy_files requires "from" and "to" keyword arguments')
		
	return _rename_or_copy_files(build, kw['from'], kw['to'], rename=False, ignore_patterns=kw.get('ignore_patterns'))

@task
def _rename_or_copy_files(build, frm, to, rename=True, ignore_patterns=None):
	if ignore_patterns is None:
		ignore_patterns = []

	from_, to = utils.render_string(build.config, frm), utils.render_string(build.config, to)
	ignore_func = shutil.ignore_patterns(*ignore_patterns)

	if rename:
		build.log.debug('renaming {from_} to {to}'.format(**locals()))
		shutil.move(from_, to)
	else:
		if '*' in to:
			# looks like a glob - last directory in path might not exist.
			tos = glob.glob(path.dirname(to))
			tos = [path.join(t,path.basename(to)) for t in tos]
		else:
			# don't glob in case the to path doesn't exist yet
			tos = [to]
		
		for found_to in tos:
			build.log.debug('copying {from_} to {found_to}'.format(**locals()))
			if path.isdir(from_):
				shutil.copytree(from_, found_to, ignore=ignore_func)
			else:
				shutil.copy(from_, found_to)

@task
def find_and_replace(build, *files, **kwargs):
	'''replace one string with another in a set of files
	
	:param kwargs: must contain ``find`` and ``replace`` keys, 
	representing the string to look for, and string to replace
	with, respectively.
	
	:param kwargs: can also contain the ``template`` boolean
	argument, which determines if we will run the ``replace``
	argument through genshi templating first (defaults to True).
	
	:param files: array of glob patterns to select files
	:param kwargs: must contain ``find`` and ``replace`` keys
	'''
	build.log.info('find and replace to %d patterns' % len(files))

	if "find" not in kwargs:
		raise ConfigurationError("Find not passed in to find_and_replace")
	if "replace" not in kwargs:
		raise ConfigurationError("Replace not passed in to find_and_replace")
	template = kwargs.get('template', True)
	find = kwargs["find"]
	replace = kwargs['replace']
	if template:
		replace = utils.render_string(build.config, replace)

	replace_summary = replace[:60]+'...' if len(replace) > 60 else replace
	build.log.debug("replacing %s with %s" % (find, repr(replace_summary)))

	for glob_str in files:
		found_files = glob.glob(utils.render_string(build.config, glob_str))
		if len(found_files) == 0:
			build.log.warning('No files were found to match pattern "%s"' % glob_str)
		for _file in found_files:
			_replace_in_file(build, _file, find, replace)

@task
def find_and_replace_in_dir(build, root_dir, find, replace, file_suffixes=("html",), template=False, **kw):
	'For all files ending with one of the suffixes, under the root_dir, replace ``find`` with ``replace``'
	if template:
		replace = utils.render_string(build.config, replace)

	build.log.debug("replacing {find} with {replace} in {files}".format(
		find=find, replace=replace, files="{0}/**/*.{1}".format(root_dir, file_suffixes)
	))
	
	found_roots = glob.glob(root_dir)
	if len(found_roots) == 0:
		build.log.warning('No files were found to match pattern "%s"' % root_dir)
	for found_root in found_roots:
		for root, _, files, depth in walk_with_depth(found_root):
			for file_ in files:
				if file_.rpartition('.')[2] in file_suffixes:
					find_with_fixed_path = find.replace("%{back_to_parent}%", "../" * (depth+1))
					replace_with_fixed_path = replace.replace("%{back_to_parent}%", "../" * (depth+1))
					_replace_in_file(build, path.join(root, file_), find_with_fixed_path, replace_with_fixed_path)

def _replace_in_file(build, filename, find, replace):
	build.log.debug("replacing {find} with {replace} in {filename}".format(**locals()))
	
	tmp_file = uuid.uuid4().hex
	with codecs.open(filename, 'r', encoding='utf8') as in_file:
		in_file_contents = in_file.read()
		in_file_contents = in_file_contents.replace(find, replace)
	with codecs.open(tmp_file, 'w', encoding='utf8') as out_file:
		out_file.write(in_file_contents)
	os.remove(filename)
	os.rename(tmp_file, filename)

@task
def resolve_urls(build, *url_locations):
	'''Include "src" prefix for relative URLs, e.g. ``file.html`` -> ``src/file.html``
	
	``url_locations`` uses::
	
	* dot-notation to descend into a dictionary
	* ``[]`` at the end of a field name to denote an array
	* ``*`` means all attributes on a dictionary
	'''
	def resolve_url_with_uuid(url):
		return utils._resolve_url(build.config, url, 'src')
	for location in url_locations:
		build.config = utils.transform(build.config, location, resolve_url_with_uuid)

@task
def wrap_activations(build, location):
	'''Wrap user activation code to prevent running in frames if required
	
	'''
	for activation in build.config['activations']:
		if not 'all_frames' in activation or activation['all_frames'] is False:
			for script in activation['scripts']:
				tmp_file = uuid.uuid4().hex
				filename = location+script[3:]
				build.log.debug("wrapping activation {filename}".format(**locals()))
				with codecs.open(filename, 'r', encoding='utf8') as in_file:
					in_file_contents = in_file.read()
					in_file_contents = 'if (forge._disableFrames === undefined || window.location == window.parent.location) {\n'+in_file_contents+'\n}';
				with codecs.open(tmp_file, 'w', encoding='utf8') as out_file:
					out_file.write(in_file_contents)
				os.remove(filename)
				os.rename(tmp_file, filename)
		

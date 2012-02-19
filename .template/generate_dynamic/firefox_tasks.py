import codecs
import json
import os
import shutil
import logging

from lib import task

LOG = logging.getLogger(__name__)

def clean_firefox(build_type_dir):
	original_harness_options = os.path.join(build_type_dir, 'firefox', 'harness-options.json')
	backup_harness_options = os.path.join(build_type_dir, 'firefox', 'harness-options-bak.json')
	LOG.debug('Cleaning up after firefox run')
	shutil.move(backup_harness_options, original_harness_options)

@task
def run_firefox(build, build_type_dir):
	from cuddlefish.runner import run_app

	original_harness_options = os.path.join(build_type_dir, 'firefox', 'harness-options.json')
	backup_harness_options = os.path.join(build_type_dir, 'firefox', 'harness-options-bak.json')
	shutil.move(original_harness_options, backup_harness_options)
	try:
		with codecs.open(backup_harness_options, encoding='utf8') as harness_file:
			harness_config = json.load(harness_file)
		run_app(os.path.join(build_type_dir, 'firefox'), harness_config, "firefox", verbose=True)
	finally:
		clean_firefox(build_type_dir)

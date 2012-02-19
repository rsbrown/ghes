import logging
from os import path

from lib import cd, task
from utils import run_shell

LOG = logging.getLogger(__name__)

@task
def run_web(build, build_type_dir, **kw):
	# run Node locally
	with cd(path.join("development", "web")):
		try:
			run_shell("npm", "install")
			run_shell("npm", "start", command_log_level=logging.INFO)
		except Exception:
			LOG.error("failed to run npm: do you have Node.js installed and on your path?")
			raise

@task
def package_web(build, **kw):
	# deploy to Heroku
	print 'package web', build, kw

import codecs
import datetime
from glob import glob
import logging
import os
from os import path
import plistlib
import re
import signal
import subprocess
import tempfile
import time
import uuid

import lib
from lib import task
from utils import run_shell

LOG = logging.getLogger(__name__)

class IOSError(Exception):
	pass

class IOSRunner(object):
	def __init__(self, path_to_ios_build):
		# TODO: should allow us to cd straight to where the ios build is
		# at the moment this points one level above, e.g. my-app/development,
		# NOT my-app/development/ios
		self.path_to_ios_build = path_to_ios_build

		self.log_process = None

	def setup_simulator(self):
		self.sdk = '/Developer/Platforms/iPhoneSimulator.platform/Developer/Applications/iPhone Simulator.app/Contents/MacOS'

		if not path.exists(self.sdk):
			raise IOError("Couldn't find the iPhone sdk at: %s" % self.sdk) 

	@staticmethod
	def get_child_processes(target_parent_pid):
		'Gets processes which have the given pid as their parent'
		# scrape processes for those with the iphone simulator as the parent
		list_processes = subprocess.Popen('ps ax -o "pid= ppid="', shell=True, stdout=subprocess.PIPE)

		child_pids = []

		for line in list_processes.stdout:
			line = line.strip()
			if line != "":
				pid, parent_pid = map(int, line.split())
				if parent_pid == target_parent_pid:
					child_pids.append(pid)

		return child_pids

	def start_piping_system_log(self, app_name, pid):
		# don't use sed to avoid zombie processes
		self.log_process = subprocess.Popen(r"tail -f /var/log/system.log | grep --line-buffered '\[%s' | egrep -o 'Message: .+'" % pid, shell=True)
		# old version, which matched output format to other platforms, but left sed lying around
		# self.log_process = subprocess.Popen(r"tail -f /var/log/system.log | grep --line-buffered '\[%s' | sed -E 's/([^ ]+ [^ ]+ [^ ]+).*\]: (.*)/[\1] \2/'" % pid, shell=True)
		LOG.debug('log watcher PID: {0}'.format(self.log_process.pid))
		LOG.info('Showing log output:')
		
	def _grab_plist_from_binary_mess(self, file_path):
		start_marker = '<?xml version="1.0" encoding="UTF-8"?>'
		end_marker = '</plist>'
		
		with open(file_path, 'rb') as plist_file:
			plist = plist_file.read()
		start = plist.find(start_marker)
		end = plist.find(end_marker)
		if start < 0 or end < 0:
			raise ValueError("{0} does not appear to be a valid provisioning profile".format(file_path))
		
		real_plist = plist[start:end+len(end_marker)]
		return real_plist
	
	def _parse_plist(self, plist):
		return plistlib.readPlistFromString(plist)
		
	def _extract_seed_id(self, plist_dict):
		'E.g. "DEADBEEDAA" from provisioning profile plist including "DEADBEEDAA.*"'
		app_ids = plist_dict["ApplicationIdentifierPrefix"]
		if not app_ids:
			raise ValueError("Couldn't find an 'ApplicationIdentifierPrefix' entry in your provisioning profile")
		return app_ids[0]

	def _extract_app_id(self, plist_dict):
		'E.g. "DEADBEEFAA.io.trigger.forge.app" from provisioning profile plist, only works for distribution profiles'
		entitlements = plist_dict["Entitlements"]
		if not entitlements:
			raise ValueError("Couldn't find an 'Entitlements' entry in your provisioning profile")
		app_id = entitlements['application-identifier']
		if not app_id:
			raise ValueError("Couldn't find an 'application-identifier' entry in your provisioning profile")
		return app_id
	
	def _is_distribution_profile(self, plist_dict):
		'See if the profile as any ProvisionedDevices, if not it is distribution'
		return 'ProvisionedDevices' not in plist_dict

	def _check_for_codesign(self):
		which_codesign = subprocess.Popen(['which', 'codesign'], stdout=subprocess.PIPE)
		stdout, stderr = which_codesign.communicate()
		
		if which_codesign.returncode != 0:
			raise IOError("Couldn't find the codesign command. Make sure you have xcode installed and codesign in your PATH.")
		return stdout.strip()

	def get_bundled_ai(self, plist_dict, path_to_ios_build):
		'''
		returns the application identifier, with bundle id
		'''
		import biplist
		info_plist_path = glob(path_to_ios_build + '/ios' + '/device-*')[0] + '/Info.plist'
		return "%s.%s" % (
			plist_dict['ApplicationIdentifierPrefix'][0],
			biplist.readPlist(info_plist_path)['CFBundleIdentifier']
		)

	def check_plist_dict(self,plist_dict, path_to_ios_build):
		'''
		Raises an IOSError on:
		 - Expired profile
		 - Ad-Hoc profile
		 - invalid Entitlements
		'''
		if plist_dict['ExpirationDate'] < datetime.datetime.now():
			raise IOSError("Provisioning profile has expired")
			
		if not plist_dict['Entitlements']['get-task-allow']:
			raise IOSError("Ad-hoc profiles are not supported")
		
		ai = plist_dict['Entitlements']['application-identifier']
		
		bundled_ai = self.get_bundled_ai(plist_dict, path_to_ios_build)
		wildcard_ai = "%s.*" % plist_dict['ApplicationIdentifierPrefix'][0]
		
		LOG.info(bundled_ai)
		LOG.info(ai)
		if not (ai == bundled_ai or ai == wildcard_ai):
			raise IOSError('Invalid entitlements in provisioning profile "%s".' % (ai))

		
	def log_profile(self, plist_dict):
		'''
		Logs:
		name
		number of enabled devices (with ids)
		appstore profile or development
		'''
		LOG.info('Application Identifier: ' + plist_dict['ApplicationIdentifierPrefix'][0])
		
		if len(plist_dict['ProvisionedDevices']) > 0:
			
			LOG.info(str(len(plist_dict['ProvisionedDevices'])) + ' Provisioned Device(s):')
			LOG.info(plist_dict['ProvisionedDevices'])
		else:
			LOG.info('No Provisioned Devices, profile is Appstore')

	def create_ipa_from_app(self, build, provisioning_profile, certificate_to_sign_with=None, relative_path_to_itunes_artwork=None):
		"""Create an ipa from an app, with an embedded provisioning profile provided by the user, and 
		signed with a certificate provided by the user.

		:param build: instance of build
		:param provisioning_profile: Absolute path to the provisioning profile to embed in the ipa
		:param certificate_to_sign_with: (Optional) The name of the certificate to sign the ipa with
		:param relative_path_to_itunes_artwork: (Optional) A path to a 512x512 png picture for the App view in iTunes.
			This should be relative to the location of the user assets.
		"""
		# XXX
		# TODO: refactor _copy and _replace_in_file into common utility file
		def _copy(item, into):
			# XXX not platform agnostic!
			if item[-1] == '/':
				item = item[:-1]
			run_shell('/bin/cp', '-Rp', item, into)
		
		def _replace_in_file(filename, find, replace):
			tmp_file = uuid.uuid4().hex
			with codecs.open(filename, 'r', encoding='utf8') as in_file:
				in_file_contents = in_file.read()
				in_file_contents = in_file_contents.replace(find, replace)
			with codecs.open(tmp_file, 'w', encoding='utf8') as out_file:
				out_file.write(in_file_contents)
			os.remove(filename)
			os.rename(tmp_file, filename)

		LOG.info('Starting package process for iOS')
		
		if certificate_to_sign_with is None:
			certificate_to_sign_with = 'iPhone Developer'

		file_name = "{name}-{time}.ipa".format(
			name=re.sub("[^a-zA-Z0-9]", "", build.config["name"].lower()),
			time=str(int(time.time()))
		)
		output_path_for_ipa = path.abspath(path.join('release', 'ios', file_name))
		directory = path.dirname(output_path_for_ipa)
		if not path.isdir(directory):
			os.makedirs(directory)

		app_folder_name = self._locate_ios_app(error_message="Couldn't find iOS app in order to sign it")
		path_to_template_app = path.join(self.path_to_ios_build, '..', '.template', 'ios', app_folder_name)
		path_to_app = path.join(self.path_to_ios_build, 'ios', app_folder_name)
		generate_dynamic_root = path.join(self.path_to_ios_build, '..', '.template', 'generate_dynamic')
		
		# Verify current signature
		codesign = self._check_for_codesign()
		run_shell(codesign, '--verify', '-vvvv', path_to_template_app)
		
		LOG.info('going to package: %s' % path_to_app)
		
		plist_str = self._grab_plist_from_binary_mess(provisioning_profile)
		plist_dict = self._parse_plist(plist_str)
		self.check_plist_dict(plist_dict, self.path_to_ios_build)
		LOG.info("Plist OK.")
		
		self.log_profile(plist_dict)
		
		seed_id = self._extract_seed_id(plist_dict)
		
		LOG.debug("extracted seed ID: {0}".format(seed_id))
		
		temp_dir = tempfile.mkdtemp()
		with lib.cd(temp_dir):
			LOG.debug('Moved into tempdir: %s' % temp_dir)
			embedded_profile = 'embedded.mobileprovision'
			path_to_new_profile = provisioning_profile

			LOG.debug('Making Payload directory')
			os.mkdir('Payload')

			path_to_payload = path.join(temp_dir, 'Payload')
			path_to_embedded_profile = path.join(path_to_payload, app_folder_name, embedded_profile)
			path_to_payload_app = path.join(path_to_payload, app_folder_name)
			path_to_resource_rules = path.join(path_to_payload_app, 'ResourceRules.plist')

			if relative_path_to_itunes_artwork is not None:
				path_to_itunes_artwork = path.join(path_to_payload_app, 'assets', 'src', relative_path_to_itunes_artwork)
			else:
				path_to_itunes_artwork = None

			_copy(path_to_app, path_to_payload)
			run_shell('/bin/rm', '-rf', path_to_embedded_profile)
			_copy(path_to_new_profile, path_to_embedded_profile)
			
			if self._is_distribution_profile(plist_dict):
				bundle_id = self._extract_app_id(plist_dict)
				_copy(path.join(generate_dynamic_root, 'template.entitlements'), temp_dir)
				_replace_in_file(path.join(temp_dir, 'template.entitlements'), 'APP_ID', bundle_id)
				run_shell(codesign, '--force', '--preserve-metadata',
					'--sign', certificate_to_sign_with,
						'--entitlements', path.join(temp_dir, 'template.entitlements'),
					'--resource-rules={0}'.format(path_to_resource_rules),
					path_to_payload_app)
			else:
				run_shell(codesign, '--force', '--preserve-metadata',
						'--entitlements', path.join(generate_dynamic_root, 'dev.entitlements'),
						'--sign', certificate_to_sign_with,
						'--resource-rules={0}'.format(path_to_resource_rules),
						path_to_payload_app)
			if path_to_itunes_artwork:
				_copy(path_to_itunes_artwork, path.join(temp_dir, 'iTunesArtwork'))

			run_shell('/usr/bin/zip', '--symlinks', '--verbose', '--recurse-paths', output_path_for_ipa, '.')
		LOG.info("created IPA: {output}".format(output=output_path_for_ipa))
		return output_path_for_ipa

	def _locate_ios_app(self, error_message):
		ios_build_dir = path.join(self.path_to_ios_build, 'ios')
		with lib.cd(ios_build_dir):
			possible_apps = glob('device-*.app/')

			if not possible_apps:
				raise IOError(error_message)

			return possible_apps[0]

	def run_iphone_simulator_with(self, app_name):
		app_pid = None
		possible_app_location = '{0}/ios/simulator-*/Forge'.format(self.path_to_ios_build)
		LOG.debug('Looking for apps at {0}'.format(possible_app_location))
		possible_apps = glob(possible_app_location)
		if not possible_apps:
			raise IOError("Couldn't find iOS app to run it in the simulator, you may need to enable iOS builds: run wm-dev-build --full to fetch a new build")
		
		path_to_app = possible_apps[0]
		self.setup_simulator()
		
		try:
			path_to_simulator = path.join(self.sdk, "iPhone Simulator")
			path_to_file = path.abspath(path_to_app)

			LOG.debug('trying to run app %s' % path_to_file)
			simulator = subprocess.Popen([path_to_simulator, "-SimulateApplication", path_to_file])
			LOG.info('simulator pid is %s' % simulator.pid)

			# XXX: race condition, the app may not have started yet, so we try a few times.
			attempts = 0

			while app_pid is None:
				time.sleep(0.5)
				child_processes = self.get_child_processes(simulator.pid)

				if child_processes:
					app_pid = child_processes[0]
					LOG.info("pid for iPhone app is: %s" % app_pid)
					break

				if app_pid is None:
					attempts += 1

				if attempts > 10:
					LOG.warning("failed to get pid for the app being simulated. This means we can't kill it on shutdown, so you may have to kill it yourself using Activity Monitor")
					break

			self.start_piping_system_log(app_name, app_pid)
			simulator.communicate()

		finally:
			if app_pid is not None:
				try:
					LOG.debug('sending kill signal to simulated app ({0})...'.format(app_pid))
					os.kill(app_pid, signal.SIGTERM)
				except OSError:
					LOG.info("simulated app not running for us to kill")
				if self.log_process:
					try:
						LOG.debug("terminating log watcher ({0})...".format(self.log_process.pid))
						self.log_process.kill()
					except OSError as e:
						LOG.info(e)
			else:
				LOG.warning("""
     _               
 ___| |_   ___  _ __  
/ __| __| / _ \| '_ \ 
\__ \ |_ | (_) | |_) |
|___/\__| \___/| .__/ 
               |_|""")
				LOG.warning("We were unable to stop the previous simulated application: look in Activity Monitor for your app name and kill the process!")

@task
def run_ios(build, path_to_ios_build):
	runner = IOSRunner(path_to_ios_build)
	runner.run_iphone_simulator_with(build.config['name'])

@task
def package_ios(build, path_to_ios_build, provisioning_profile, certificate_to_sign_with=None, **kw):
	runner = IOSRunner(path_to_ios_build)
	try:
		relative_path_to_itunes_artwork = build.config['icons']['512']
	except KeyError:
		relative_path_to_itunes_artwork = None

	runner.create_ipa_from_app(
		build=build,
		provisioning_profile=provisioning_profile,
		certificate_to_sign_with=certificate_to_sign_with,
		relative_path_to_itunes_artwork=relative_path_to_itunes_artwork,
	)

def _generate_package_name(build):
	if "package_names" not in build.config:
		build.config["package_names"] = {}
	if "ios" not in build.config["package_names"]:
		package_name = re.sub("[^a-zA-Z0-9]", "", build.config["name"].lower()) + build.config["uuid"]
		build.config["package_names"]["ios"] = "io.trigger.forge."+package_name
	return build.config["package_names"]["ios"]

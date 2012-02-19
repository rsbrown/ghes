from collections import namedtuple
from getpass import getpass
import logging
import os
from os import path
import re
import shutil
from subprocess import Popen, PIPE, STDOUT
import sys
import tempfile
import time
import urllib
import zipfile

from lib import cd, task, CouldNotLocate
from utils import run_shell

LOG = logging.getLogger(__name__)

class AndroidError(Exception):
	pass

PathInfo = namedtuple('PathInfo', 'android adb sdk')

def _look_for_java():
	possible_jre_locations = [
		r"C:\Program Files\Java\jre7",
		r"C:\Program Files\Java\jre6",
		r"C:\Program Files (x86)\Java\jre7",
		r"C:\Program Files (x86)\Java\jre6",
	]

	return [directory for directory in possible_jre_locations if path.isdir(directory)]

def _download_sdk_for_windows():
	urllib.urlretrieve("https://trigger.io/redirect/android/windows", "sdk.zip")

	LOG.info('Download complete, extracting SDK')
	zip_to_extract = zipfile.ZipFile("sdk.zip")
	zip_to_extract.extractall("C:\\")
	zip_to_extract.close()

	# XXX: should this really be hardcoded to C:\android-sdk-windows? wasn't sure if we were allowing user to specify location..
	return PathInfo(android=r"C:\android-sdk-windows\tools\android.bat", adb=r"C:\android-sdk-windows\platform-tools\adb", sdk=r"C:\android-sdk-windows")

def _download_sdk_for_mac():
	urllib.urlretrieve("https://trigger.io/redirect/android/macosx", "sdk.zip")

	LOG.info('Download complete, extracting SDK')
	zip_process = Popen(["unzip", "sdk.zip", '-d', "/Applications"], stdout=PIPE, stderr=STDOUT)
	output = zip_process.communicate()[0]
	LOG.debug("unzip output")
	LOG.debug(output)

	return PathInfo(android="/Applications/android-sdk-macosx/tools/android", adb="/Applications/android-sdk-macosx/platform-tools/adb", sdk="/Applications/android-sdk-macosx")

def _download_sdk_for_linux():
	urllib.urlretrieve("https://trigger.io/redirect/android/linux", "sdk.tgz")

	LOG.info('Download complete, extracting SDK')
	if not path.isdir(path.expanduser("~/.forge")):
		os.mkdir(path.expanduser("~/.forge"))

	zip_process = Popen(["tar", "zxf", "sdk.tgz", "-C", path.expanduser("~/.forge")], stdout=PIPE, stderr=STDOUT)
	output = zip_process.communicate()[0]
	LOG.debug("unzip output")
	LOG.debug(output)

	return PathInfo(
		android=path.expanduser("~/.forge/android-sdk-linux/tools/android"),
		adb=path.expanduser("~/.forge/android-sdk-linux/platform-tools/adb"),
		sdk=path.expanduser("~/.forge/android-sdk-linux"),
	)

def _install_sdk_automatically():
	# Attempt download
	orig_dir = os.getcwd()
	temp_d = tempfile.mkdtemp()
	try:
		os.chdir(temp_d)
		LOG.info('Downloading Android SDK (about 30MB, may take some time)')

		if sys.platform.startswith('win'):
			path_info = _download_sdk_for_windows()
		elif sys.platform.startswith('darwin'):
			path_info = _download_sdk_for_mac()
		elif sys.platform.startswith('linux'):
			path_info = _download_sdk_for_linux()

		_update_sdk(path_info)
	except Exception, e:
		LOG.error(e)
		raise CouldNotLocate("Automatic SDK download failed, please install manually and specify with the --sdk flag")
	else:
		LOG.info('Android SDK update complete')
		return _check_for_sdk()
	finally:
		os.chdir(orig_dir)
		shutil.rmtree(temp_d, ignore_errors=True)

def _update_sdk(path_info):
	LOG.info('Updating SDK and downloading required Android platform (about 90MB, may take some time)')
	with open(os.devnull, 'w') as devnull:
		android_process = Popen(
			[path_info.android, "update", "sdk", "--no-ui", "--filter", "platform-tool,tool,android-8"],
			stdout=devnull,
			stderr=devnull,
		)
		while android_process.poll() is None:
			time.sleep(5)
			try:
				Popen([path_info.adb, "kill-server"], stdout=devnull, stderr=devnull)
			except Exception:
				pass

def _should_install_sdk(sdk_path):
	resp = raw_input('''
No Android SDK found, would you like to:

(1) Attempt to download and install the SDK automatically to {sdk_path}, or,
(2) Install the SDK yourself and rerun this command with the --sdk option to specify its location.

Please enter 1 or 2: '''.format(sdk_path=sdk_path))

	return resp == "1"

def _prompt_user_to_attach_device(path_info):
	"Prompt to automatically (create and) run an AVD"
	prompt = raw_input('''
No active Android device found, would you like to:

(1) Attempt to automatically launch the Android emulator
(2) Attempt to find the device again (choose this option after plugging in an Android device or launching the emulator).

Please enter 1 or 2: ''')

	if not prompt == "1":
		return

	_create_avd_if_necessary(path_info)
	_launch_avd(path_info)

def _check_for_sdk(dir=None, interactive=True):
	# Some sensible places to look for the Android SDK
	possible_sdk = [
		"C:/Program Files (x86)/Android/android-sdk/",
		"C:/Program Files/Android/android-sdk/",
		"C:/Android/android-sdk/",
		"C:/Android/android-sdk-windows/",
		"C:/android-sdk-windows/",
		"/Applications/android-sdk-macosx",
		path.expanduser("~/.forge/android-sdk-linux")
	]
	if dir:
		possible_sdk.insert(0, dir)

	for directory in possible_sdk:
		if path.isdir(directory):
			return directory if directory.endswith('/') else directory+'/'
	else:
		# No SDK found - will the user let us install one?
		sdk_path = None
		
		if sys.platform.startswith('win'):
			sdk_path = "C:\\android-sdk-windows"
		elif sys.platform.startswith('linux'):
			sdk_path = path.expanduser("~/.forge/android-sdk-linux")
		elif sys.platform.startswith('darwin'):
			sdk_path = "/Applications/android-sdk-macosx"
			
		if not sdk_path:
			raise CouldNotLocate("No Android SDK found, please specify with the --sdk flag")
		
		if interactive:
			if _should_install_sdk(sdk_path):
				return _install_sdk_automatically()
			else:
				raise CouldNotLocate("No Android SDK found: please install one and use the --sdk flag")
		else:
			raise AndroidError("No Android SDK found, please specify one in your global settings")


def _scrape_available_devices(text):
	'Scrapes the output of the adb devices command into a list'
	lines = text.split('\n')
	available_devices = []

	for line in lines:
		words = line.split('\t')

		if len(words[0]) > 5 and words[0].find(" ") == -1:
			available_devices.append(words[0])

	return available_devices

def run_background(args, detach=False):
	if sys.platform.startswith('win'):
		# Windows only
		DETACHED_PROCESS = 0x00000008
		Popen(args, creationflags=DETACHED_PROCESS)
	else:
		if detach:
			os.system("bash -i -c '"+" ".join(args)+" &' &")
		else:
			os.system(" ".join(args)+" &")

def check_for_java():
	'Return True java exists on the path and can be invoked; False otherwise'
	with open(os.devnull, 'w') as devnull:
		try:
			proc = Popen(['java', '-version'], stdout=devnull, stderr=devnull)
			proc_std = proc.communicate()[0]
			return proc.returncode == 0
		except:
			return False

def _create_avd(path_info):
	LOG.info('Creating AVD')
	args = [
		path_info.android,
		"create",
		"avd",
		"-n", "forge",
		"-t", "android-8",
		"--skin", "HVGA",
		"-p", path.join(path_info.sdk, 'forge-avd'),
		#"-a",
		"-c", "32M",
		"--force"
	]
	proc = Popen(args, stdin=PIPE, stdout=PIPE, stderr=STDOUT)
	time.sleep(0.1)
	proc_std = proc.communicate(input='\n')[0]
	if proc.returncode != 0:
		LOG.error('failed: %s' % (proc_std))
		raise AndroidError
	LOG.debug('Output:\n'+proc_std)

def _launch_avd(path_info):
	with cd(path.join(path.pardir, path.pardir)):
		run_background([path.join(path_info.sdk, "tools", "emulator"), "-avd", "forge"], detach=True)
	
	LOG.info("Started emulator, waiting for device to boot")
	args = [
		path_info.adb,
		"wait-for-device"
	]
	run_shell(*args)
	args = [
		path_info.adb,
		"shell", "pm", "path", "android"
	]
	output = "Error:"
	while output.startswith("Error:"):
		output = run_shell(*args)

def _zip_apk():
	LOG.info('Zipping files')
	zipf = None
	zipf_name = 'app.apk'
	try:
		zipf = zipfile.ZipFile(zipf_name, mode='w')
		for root, _, files in os.walk('.'):
			if root == '.':
				root = ''
			else: 
				root = root.replace('\\', '/')+"/"
				if root[0:2] == './':
					root = root[2:]
			for f in files:
				if f != zipf_name:
					LOG.debug('zipping: %s' % f)
					zipf.write(root+f, root+f)
	finally:
		if zipf:
			zipf.close()
			
	return zipf_name

def _sign_zipf(jre, keystore, storepass, keyalias, keypass, signed_zipf_name, zipf_name):
	generate_dynamic_root = path.join(
		os.getcwd(), path.pardir, path.pardir,
		".template", "generate_dynamic",
	)
	
	args = [
		path.join(jre,'java'),
		'-jar',
		path.join(generate_dynamic_root, 'apk-signer.jar'),
		'--keystore',
		keystore,
		'--storepass',
		storepass,
		'--keyalias',
		keyalias,
		'--keypass',
		keypass,
		'--out',
		signed_zipf_name,
		zipf_name
	]
	run_shell(*args)

def _sign_zipf_debug(jre, zipf_name, signed_zipf_name):
	LOG.info('Signing APK with a debug key')

	generate_dynamic_root = path.join(
		os.getcwd(), path.pardir, path.pardir,
		".template", "generate_dynamic",
	)
	return _sign_zipf(
		jre=jre,
		keystore=path.join(generate_dynamic_root, 'debug.keystore'),
		storepass="android",
		keyalias="androiddebugkey",
		keypass="android",
		signed_zipf_name=signed_zipf_name,
		zipf_name=zipf_name,
	)

def _sign_zipf_release(jre, zipf_name, signed_zipf_name, keystore, storepass, keyalias, keypass):
	LOG.info('Signing APK with your release key')
	return _sign_zipf(
		jre=jre,
		keystore=keystore,
		storepass=storepass,
		keyalias=keyalias,
		keypass=keypass,
		signed_zipf_name=signed_zipf_name,
		zipf_name=zipf_name,
	)
	
def _align_apk(sdk, signed_zipf_name, out_apk_name):
	LOG.info('Aligning apk')
	if path.exists(out_apk_name):
		os.remove(out_apk_name)
	args = [path.join(sdk, 'tools', 'zipalign'), '-v', '4', signed_zipf_name, out_apk_name]
	run_shell(*args)

def _generate_package_name(build):
	if "package_names" not in build.config:
		build.config["package_names"] = {}
	if "android" not in build.config["package_names"]:
		package_name = re.sub("[^a-zA-Z0-9]", "", build.config["name"].lower()) + build.config["uuid"]
		build.config["package_names"]["android"] = "io.trigger.forge."+package_name
	return build.config["package_names"]["android"]

def _run_apk(sdk, chosen_device, package_name):
	LOG.info('Running apk')
	# Get the app config details
	args = [sdk+'platform-tools/adb', '-s', chosen_device, 'shell', 'am', 'start', '-n', package_name+'/'+package_name+'.LoadActivity']
	run_shell(*args)
	
def _follow_log(sdk, chosen_device):
	LOG.info('Clearing android log')
	args = [sdk+'platform-tools/adb', '-s', chosen_device, 'logcat', '-c']
	proc = Popen(args, stdout=sys.stdout, stderr=sys.stderr)
	proc.wait()
	LOG.info('Showing android log')
	args = [sdk+'platform-tools/adb', '-s', chosen_device, 'logcat', 'WebCore:D', 'Forge:D', '*:S']
	proc = Popen(args, stdout=sys.stdout, stderr=sys.stderr)
	proc.wait()

def _create_avd_if_necessary(path_info):
	# Create avd
	LOG.info('Checking for previously created AVD')
	if path.isdir(path.join(path_info.sdk, 'forge-avd')):
		LOG.info('Existing AVD found')
	else:
		_create_avd(path_info)

def clean_android(sdk):
	"""Clean up after an android run.

	This just kills adb which holds a lock on the apk file last run, and prevents future dev-builds.
	"""
	LOG.debug('Cleaning up after android run')
	sdk = _check_for_sdk(sdk, interactive=False)
	path_info = _create_path_info_from_sdk(sdk)
	run_background([path_info.adb, 'kill-server'])

def _create_path_info_from_sdk(sdk):
	return PathInfo(
		android=path.abspath(path.join(
			sdk,
			'tools',
			'android.bat' if sys.platform.startswith('win') else 'android'
		)),
		adb=path.abspath(path.join(sdk, 'platform-tools', 'adb')),
		sdk=sdk,
	)

@task
def run_android(build, build_type_dir, sdk, device, interactive=True):
	sdk = _check_for_sdk(sdk, interactive=interactive)
	jre = ""

	if not check_for_java():
		jres = _look_for_java()
		if not jres:
			raise AndroidError("Java not found: Java must be installed and available in your path in order to run Android")
		jre = path.join(jres[0], 'bin')

	path_info = _create_path_info_from_sdk(sdk)

	try:
		run_background([path_info.adb, 'kill-server'])

		LOG.info('Looking for Android device')
		orig_dir = os.getcwd()
		os.chdir(path.join(build_type_dir, 'android'))
		
		run_background([path_info.adb, 'start-server'])
		time.sleep(1)

		try:
			proc = Popen([path_info.adb, 'devices'], stdout=PIPE)
		except Exception as e:
			LOG.error("problem finding the android debug bridge at: %s" % path_info.adb)
			# XXX: prompt to run the sdk manager, then retry?
			LOG.error("this probably means you need to run the Android SDK manager and download the Android platform-tools.")
			raise AndroidError
	
		proc_std = proc.communicate()[0]
		if proc.returncode != 0:
			LOG.error('Communication with adb failed: %s' % (proc_std))
			raise AndroidError

		available_devices = _scrape_available_devices(proc_std)

		if not available_devices:
			# TODO: allow for prompting of user in either webui situation or commandline situation
			if interactive:
				_prompt_user_to_attach_device(path_info)
			else:
				_create_avd_if_necessary(path_info)
				_launch_avd(path_info)

			os.chdir(orig_dir)
			return run_android(build, build_type_dir, sdk, device, interactive=interactive)

		if device:
			if device in available_devices:
				chosen_device = device
				LOG.info('Using specified android device %s' % chosen_device)
			else:
				LOG.error('No such device "%s"' % device)
				LOG.error('The available devices are:')
				LOG.error("\n".join(available_devices))
				raise AndroidError
		else:
			chosen_device = available_devices[0]
			LOG.info('No android device specified, defaulting to %s' % chosen_device)
		
		LOG.info('Creating Android .apk file')
		#zip
		zipf_name = _zip_apk()
		signed_zipf_name = 'signed-{0}'.format(zipf_name)
		out_apk_name = 'out.apk'
		
		#sign
		_sign_zipf_debug(jre, zipf_name, signed_zipf_name)
	
		#align
		_align_apk(sdk, signed_zipf_name, out_apk_name)
		LOG.debug('removing zipfile and un-aligned APK')
		os.remove(zipf_name)
		os.remove(signed_zipf_name)

		#install
		LOG.info('Installing apk')
		args = [sdk+'platform-tools/adb', '-s', chosen_device, 'install', '-r', out_apk_name]
		run_shell(*args)
	
		package_name = _generate_package_name(build)
		
		#run
		_run_apk(sdk, chosen_device, package_name)
		
		#follow log
		_follow_log(sdk, chosen_device)
	finally:
		clean_android(sdk)

def _create_output_directory(output):
	'output might be in some other directory which does not yet exist'
	directory = path.dirname(output)
	if not path.isdir(directory):
		os.makedirs(directory)

@task
def package_android(build, sdk, interactive=True, keystore=None, storepass=None, keyalias=None, keypass=None):
	SigningInfoPrompt = namedtuple('SigningInfoPrompt', 'name description secure')
	signing_info = {}
	file_name = "{name}-{time}.apk".format(
		name=re.sub("[^a-zA-Z0-9]", "", build.config["name"].lower()),
		time=str(int(time.time()))
	)
	output = path.abspath(path.join('release', 'android', file_name))
	
	if not interactive and not all(keystore, storepass, keyalias, keypass):
		raise AndroidError("When running in non-interactive mode, keystore, storepass, keyalias and keypass arguments must be supplied")
	
	signing_info["keystore"] = keystore
	signing_info["storepass"] = storepass
	signing_info["keyalias"] = keyalias
	signing_info["keypass"] = keypass
	
	if interactive:
		signing_prompts = (
			SigningInfoPrompt(name="keystore", description="the location of your release keystore", secure=False),
			SigningInfoPrompt(name="storepass", description="the password of your release keystore", secure=True),
			SigningInfoPrompt(name="keyalias", description="the alias of your release key", secure=False),
			SigningInfoPrompt(name="keypass", description="the password for your release key", secure=True),
		)
		for prompt in signing_prompts:
			if signing_info[prompt.name]:
				# value given as function parameter
				continue
				
			response = ""
			while not response:
				msg = "Please enter {0}: ".format(prompt.description)
				if prompt.secure:
					response = getpass(msg)
				else:
					response = raw_input(msg)
			signing_info[prompt.name] = response
	
	sdk = _check_for_sdk(sdk, interactive=interactive)
	jre = ""

	if not check_for_java():
		jres = _look_for_java()
		if not jres:
			raise AndroidError("Java not found: Java must be installed and available in your path in order to run Android")
		jre = path.join(jres[0], 'bin')

	try:
		orig_dir = os.getcwd()
		os.chdir(path.join('development', 'android'))

		LOG.info('Creating Android .apk file')
		#zip
		zipf_name = _zip_apk()
		signed_zipf_name = 'signed-{0}'.format(zipf_name)
		
		#sign
		_sign_zipf_release(jre, zipf_name, signed_zipf_name, **signing_info)
	
		# create output directory for APK if necessary
		_create_output_directory(output)

		#align
		_align_apk(sdk, signed_zipf_name, output)
		LOG.debug('removing zipfile and un-aligned APK')
		os.remove(zipf_name)
		os.remove(signed_zipf_name)

		LOG.info("created APK: {output}".format(output=output))
		return output
	finally:
		clean_android(sdk)
		os.chdir(orig_dir)


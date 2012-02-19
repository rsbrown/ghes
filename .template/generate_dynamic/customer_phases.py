"Tasks that might be run on the customers's machine"

from os import path

# where the customer code exists inside the apps (doing a server build)
locations_for_server = {
	'android': 'android/template-app/assets/src',
	'ios': 'ios/templateapp/assets/src',
	'chrome': 'chrome/src',
	'firefox': 'firefox/template-app/data/src',
	'safari': 'forge.safariextension/src',
	'ie': 'ie/src',
	'web': 'web/src',
}

# where the customer code exists inside the apps (doing a customer-local build)
locations_for_customer = {
	'android': 'development/android/assets/src',
	'ios': 'development/ios/*/assets/src',
	'chrome': 'development/chrome/src',
	'firefox': 'development/firefox/resources/*-at-jetpack-f-data/src',
	'safari': 'development/forge.safariextension/src',
	'ie': 'development/ie/src',
	'web': 'development/web/src',
}

def copy_user_source_to_template(server=False, ignore_patterns=None):
	locations = locations_for_server if server else locations_for_customer
	
	return [
		('android', 'include_user', 'copy_files', (), { 'from': 'src', 'to': locations["android"], 'ignore_patterns': ignore_patterns }),
		('ios','include_user', 'copy_files', (), { 'from': 'src', 'to': locations["ios"], 'ignore_patterns': ignore_patterns }),
		('chrome', 'include_user', 'copy_files', (), {'from': 'src', 'to': locations["chrome"], 'ignore_patterns': ignore_patterns }),
		('firefox', 'include_user', 'copy_files', (), {'from': 'src', 'to': locations["firefox"], 'ignore_patterns': ignore_patterns }),
		('safari', 'include_user', 'copy_files', (), {'from': 'src', 'to': locations["safari"], 'ignore_patterns': ignore_patterns }),
		('ie', 'include_user', 'copy_files', (), {'from': 'src', 'to': locations["ie"], 'ignore_patterns': ignore_patterns }),
		('web', 'include_user', 'copy_files', (), {'from': 'src', 'to': locations["web"], 'ignore_patterns': ignore_patterns }),
	]
	
def include_platform_in_html(server=False):
	locations = locations_for_server if server else locations_for_customer

	return [
		('android', 'include_user', 'find_and_replace_in_dir',
			(locations["android"],),
			{
				"find": "<head>",
				"replace": "<head><script src='file:///android_asset/forge/all.js'></script>"
			}
		),
		('ios', 'include_user', 'find_and_replace_in_dir',
			(locations["ios"],),
			{
				"find": "<head>",
				"replace": "<head><script src='%{back_to_parent}%forge/all.js'></script>"
			}
		),
		('firefox', 'include_user', 'find_and_replace_in_dir',
			(locations["firefox"],),
			{
				"find": "<head>",
				"replace": "<head><script src='%{back_to_parent}%forge/all.js'></script>"
			}
		),
		('chrome', 'include_user', 'find_and_replace_in_dir',
			(locations["chrome"],),
			{
				"find": "<head>",
				"replace": "<head><script src='/forge/all.js'></script>"
			}
		),
		('safari', 'include_user', 'find_and_replace_in_dir',
			(locations["safari"],),
			{
				"find": "<head>",
				"replace": "<head><script src='%{back_to_parent}%forge/all.js'></script>"
			}
		),
		('ie', 'include_user', 'find_and_replace_in_dir',
			(locations["ie"],),
			{
				"find": "<head>",
				"replace": "<head><script src='/forge/all.js'></script>"
			}
		),
		('web', 'include_user', 'find_and_replace_in_dir',
			(locations["web"],),
			{
				"find": "<head>",
				"replace": "<head><script src='/_forge/all.js'></script>"
			}
		),
	]

def wrap_activations(server=False):
	locations = locations_for_server if server else locations_for_customer

	return [
		('firefox', 'include_user', 'wrap_activations',
			(locations["firefox"],),
		),
		('safari', 'include_user', 'wrap_activations',
			(locations["safari"],),
		),
	]

_icon_path_for_server = {
	"android": "android/template-app/res/",
	"safari": "forge.safariextension/",
	"firefox": "firefox/template-app/output/",
	"ios": "ios/"
}
_icon_path_for_customer = {
	"android": "development/android/res/",
	"safari": "development/forge.safariextension/",
	"firefox": "development/firefox/",
	"ios": "development/ios/*.app/"
}

def include_icons(server=False):
	icon_path = _icon_path_for_server if server else _icon_path_for_customer
	def icon(platform, sub_path):
		return path.join(icon_path[platform], sub_path)
	
	return [
		('android', 'have_android_icons,include_user', 'copy_files', (), {
			'from': '${icons["36"]}',
			'to': icon("android", 'drawable-ldpi/icon.png')}),
		('android', 'have_android_icons,include_user', 'copy_files', (), {
			'from': '${icons["48"]}',
			'to': icon("android", 'drawable-mdpi/icon.png')}),
		('android', 'have_android_icons,include_user', 'copy_files', (), {
			'from': '${icons["72"]}',
			'to': icon("android", "drawable-hdpi/icon.png")}),
		
		('safari', 'have_safari_icons,include_user', 'copy_files', (), {
			'from': '${icons["32"]}',
			'to': icon("safari", 'icon-32.png')}),
		('safari', 'have_safari_icons,include_user', 'copy_files', (), {
			'from': '${icons["48"]}',
			'to': icon("safari", 'icon-48.png')}),
		('safari', 'have_safari_icons,include_user', 'copy_files', (), {
			'from': '${icons["64"]}',
			'to': icon("safari", 'icon-64.png')}),
		
		('firefox', 'have_firefox_icons,include_user', 'copy_files', (), {
			'from': '${icons["32"]}',
			'to': icon("firefox", 'icon.png')}),
		('firefox', 'have_firefox_icons,include_user', 'copy_files', (), {
			'from': '${icons["64"]}',
			'to': icon("firefox", 'icon64.png')}),

		('ios', 'have_ios_icons,include_user', 'copy_files', (), {
			'from': '${icons["57"]}',
			'to': icon("ios", 'normal.png')}),
		('ios', 'have_ios_icons,include_user', 'copy_files', (), {
			'from': '${icons["72"]}',
			'to': icon("ios", 'ipad.png')}),
		('ios', 'have_ios_icons,include_user', 'copy_files', (), {
			'from': '${icons["114"]}',
			'to': icon("ios", 'retina.png')}),
			
		('ios', 'have_ios_launch,include_user', 'copy_files', (), {
			'from': '${launch_images["iphone"]}',
			'to': icon("ios", "Default~iphone.png")}),
		('ios', 'have_ios_launch,include_user', 'copy_files', (), {
			'from': '${launch_images["iphone-retina"]}',
			'to': icon("ios", "Default@2x~iphone.png")}),
		('ios', 'have_ios_launch,include_user', 'copy_files', (), {
			'from': '${launch_images["ipad"]}',
			'to': icon("ios", "Default~ipad.png")}),
		('ios', 'have_ios_launch,include_user', 'copy_files', (), {
			'from': '${launch_images["ipad-landscape"]}',
			'to': icon("ios", "Default-Landscape~ipad.png")}),
	]

def resolve_urls():
	return [
		('all', None, 'resolve_urls', (
			'activations.[].scripts.[]',
			'activations.[].styles.[]',
			'icons.*',
			'launch_images.*',
			'browser_action.default_icon',
			'browser_action.default_popup',
			'browser_action.default_icons.*',
			'page_action.default_icon',
			'page_action.default_popup',
			'page_action.default_icons.*'
		)),
	]

def run_android_phase(build_type_dir, sdk, device, **kw):
	return [
		('android', None, 'run_android', (build_type_dir, sdk, device), kw),
	]

def run_ios_phase(build_type_dir, **kw):
	return [
		('ios', None, 'run_ios', (build_type_dir,)),
	]

def run_firefox_phase(build_type_dir, **kw):
	return [
		('firefox', None, 'run_firefox', (build_type_dir,)),
	]
	
def run_web_phase(build_type_dir, **kw):
	return [
		('web', None, 'run_web', (build_type_dir,)),
	]
	
def package(build_type_dir, **kw):
	return [
		('android', None, 'package_android', (), kw),
		('ios', None, 'package_ios', (build_type_dir, ), kw),
		('web', None, 'package_web', (), kw),
	]

def make_installers(build_type_dir, **kw):
	return [
		('ie', None, 'package_ie', (build_type_dir, ), kw),
	]

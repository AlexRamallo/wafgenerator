"""
	Conan 2.0-compatible waf tool

	* `WafDeps` generates a ConfigSet file which contains package information
	  (aka uselibs, similar to how `conf.check_cfg` works)

	* `WafToolchain` generates a ConfigSet file which contains toolchain
	  information (aka settings.yml stuff), and must be processed by this waf
	  tool to modify the build environment

	Example:

	```
	$ conan install . --generator WafDeps --generator WafToolchain
	```

	followed by

	```py
	def configure(conf);
		#load this tool
		conf.load("conan")

		#Load generated dep/toolchain files into conf.env
		conf.load_conan()

		#use waf as usual
		conf.load("compiler_cxx")
	```

	In advanced scenarios, `conf.load_conan` can be instructed to load conan
	generator output from non-default paths, and write into specific waf env
	objects. This can be used for cross compiling to multiple targets at once,
	or anything else.
"""
from waflib import Utils
from waflib.Logs import warn
from waflib.Configure import conf
from waflib.Tools.compiler_c import c_compiler
from waflib.Tools.compiler_cxx import cxx_compiler
from waflib.TaskGen import feature, before_method

def configure(conf):
	pass

@feature("conan")
@before_method("process_use")
def expand_conan_targets(tg):
	"""
		This will add transient dependencies to the 'use' list so that proper
		linking can occur without having to manually track down all of the
		transient dependencies in your graph

		Rule of thumb: if something in your 'use' list refers to a conan
		package, then you should also add the "conan" feature string to the tgen
	"""
	uselist = Utils.to_list(getattr(tg, 'use', []))
	for usename in uselist:
		if (f'CONAN_USE_{usename}' in tg.env):
			deps = tg.env[f'CONAN_USE_{usename}']
		else:
			continue
		[uselist.append(r) for r in deps if r not in uselist]
	tg.use = uselist

@conf
def load_conan(
		conf,
		env = None,
		conan_deps = None,
		
		#apply compiler flags to the environment based on Conan profile. This
		#includes flags for build_type, cppstd, runtime library, etc. Unless
		#you have a very good reason, this should always be enabled.
		apply_flags = True
	):
	if not env:
		env = conf.env

	if not conan_deps:
		conan_deps = conf.path.get_bld().find_node('conan_waf_config.py')
	
	env.load(str(conan_deps))

	#add build profile bindirs to env path for `find_program` to work
	if env['CONAN_BUILD_BIN_PATH']:
		import os
		conf.environ['PATH'] = os.pathsep.join((
			conf.environ.get('PATH', ''),
			os.pathsep.join(env['CONAN_BUILD_BIN_PATH'])
		))

	for p in env['ALL_CONAN_PACKAGES']:
		conf.msg('Conan usename', p)

	if apply_flags:
		_apply_settings_flags(conf, env)
		conf_info = env['CONAN_CONFIG']
		def s(k):
			if not env[k]:
				env[k] = []
			env[k].extend(conf_info[k])
		s('DEFINES')
		s('CFLAGS')
		s('CXXFLAGS')
		s('LINKFLAGS')

def _apply_settings_flags(conf, env):
	_apply_arch(conf, env)
	_apply_os(conf, env)
	_apply_compiler(conf, env)
	_apply_cppstd(conf, env)
	_apply_build_type(conf, env)

def _apply_compiler(conf, env):
	settings = env.CONAN_SETTINGS
	compiler = settings.get('compiler', None)
	if compiler == None:
		return
	libcxx = settings.get('compiler.libcxx')
	runtime = settings.get('compiler.runtime')
	runtime_type = settings.get('compiler.runtime_type')
	threads = settings.get('compiler.threads')
	exception = settings.get('compiler.exception')

	if threads or exception:
		warn(f'WARNING: MinGW flags not handled yet!!')

	#GCC libstd ABI
	if libcxx == 'libstdc++':
		env.append_value('CXXFLAGS', '-D_GLIBCXX_USE_CXX11_ABI=0')
	elif libcxx == 'libstdc++11':
		env.append_value('CXXFLAGS', '-D_GLIBCXX_USE_CXX11_ABI=1')

	#Windows CRT
	if runtime and runtime_type:
		flag = 'M' + ('D' if runtime == 'dynamic' else 'T')
		if runtime_type == 'Debug':
			flag += 'd'
		env.append_value('CXXFLAGS', f'/{flag}')

	_override_default_compiler_selection(conf)

def _override_default_compiler_selection(conf):
	#The following adds the compiler name to the front of that c_config search
	#list(s). This activates the auto-detection feature for the compiler name.
	#Names are the names of waf tools (see waflib/Tools and waflib/extras for
	#available compilers, e.g. "clangcxx.py")

	#If a compiler isn't supported, they can be configured manually with env
	#variables, like [CC,CXX,AR,etc]. tool_requires packages with compilers can
	#provide this in their `buildenv_info`, or in the [env] section of your
	#build environment's Conan profile while calling `conan install`

	#NOTE: the following does nothing if using env for toolchain selection.

	compile_name_map = {
		#Conan name: 	(C++ name, C name)
		'clang': 		('clangxx', 'clang'),
		'apple-clang': 	('clangxx', 'clang'),
		'gcc': 			('gxx', 'gcc'),
		'msvc':			('msvc', 'msvc'),
		'sun-cc':		('suncxx', 'suncc'),
		'intel-cc':		('icpc', 'icc'),
		'qcc':			(None, None),
		'mcst-lcc':		(None, None),
	}
	compiler_name = env.CONAN_SETTINGS['compiler']
	(cxx, cc) = compile_name_map[compiler_name]

	os = env.DEST_OS
	if cxx and os in cxx_compiler:
		cxx_compiler[os].insert(0, cxx)
	
	if cc and os in c_compiler:
		c_compiler[os].insert(0, cc)

	#MSVC version and targets
	if compiler_name == 'msvc':
		#src: https://blog.knatten.org/2022/08/26/microsoft-c-versions-explained
		version = settings['compiler.version']
		msvc_ver = f'{version[:1]}.{version[-1]}'
		env['MSVC_VERSIONS'] = [f'msvc {msvc_ver}']
		env['MSVC_TARGETS'] = [env.CONAN_SETTINGS['arch']]


def _apply_cppstd(conf, env):
	cppstd = env.CONAN_SETTINGS.get('compiler.cppstd', None)
	if cppstd == None:
		return

	compiler = env.CONAN_SETTINGS['compiler']

	flags = {
		'gcc': {
			'98': 		['--std', 'c++98'],
			'gnu98': 	['--std', 'gnu++98'],
			'11':		['--std', 'c++11'],
			'gnu11':	['--std', 'gnu++11'],
			'14':		['--std', 'c++14'],
			'gnu14':	['--std', 'gnu++14'],
			'17':		['--std', 'c++17'],
			'gnu17':	['--std', 'gnu++17'],
			'20':		['--std', 'c++20'],
			'gnu20':	['--std', 'gnu++20'],
			'23':		['--std', 'c++23'],
			'gnu23':	['--std', 'gnu++23'],
		},
		'msvc': {
			'14': 		['/std:c++14'],
			'17': 		['/std:c++17'],
			'20': 		['/std:c++20'],
			'23': 		['/std:latest']
		},
	}
	if compiler not in flags:
		#gcc flags as fallback is probably fine...
		env.append_value('CXXFLAGS', flags['gcc'][cppstd])
	else:
		env.append_value('CXXFLAGS', flags[compiler][cppstd])

def _detect_default_waf_compiler_cxx(conf):
	#return the same result as waf's default compiler detect logic

	if conf.env._conan_waf_detected_default_cxx:
		return conf.env._conan_waf_detected_default_cxx

	from waflib.Tools import compiler_cxx
	
	try:
		conf.options.check_cxx_compiler
	except AttributeError:
		setattr(conf.options, 'check_cxx_compiler', None)

	conf.env.stash()
	compiler_cxx.configure(conf)
	ret = conf.env.COMPILER_CXX
	conf.env.revert()
	conf.env._conan_waf_detected_default_cxx = ret
	return ret

def _apply_build_type(conf, env):
	build_type = env.CONAN_SETTINGS.get('build_type', None)
	if build_type == None:
		return

	os = env.CONAN_SETTINGS.get('os', '')
	compiler = env.CONAN_SETTINGS.get('compiler', None)
	if compiler == None:
		_detect_default_waf_compiler_cxx(conf)

	cxxflags = []
	linkflags = []

	if compiler == 'msvc' or ('Windows' in os and compiler == 'clang'):
		if build_type == 'Debug':
			cxxflags.extend([
				'/Zi',		#generate PDBs
				'/Od',  	#disable optimizations
			])
			linkflags.extend([
				'/debug'
			])
		elif build_type == 'Release':
			cxxflags.extend([
				'/O2',		#optimize speed
				'/DNDEBUG'
			])
			linkflags.extend([
				'/incremental:no' #smaller output, functionally equivalent
			])
		elif build_type == 'RelWithDebInfo':
			cxxflags.extend([
				'/Zi',
				'/O2',
				'/DNDEBUG'
			])
			linkflags.extend([
				'/debug'
			])
		elif build_type == 'MinSizeRel':
			cxxflags.extend([
				'/O1',		#optimize size
				'/DNDEBUG'
			])
			linkflags.extend([
				'/incremental:no'
			])
	else:
		#Use GCC flags for everything else
		if build_type == 'Debug':
			cxxflags.extend([
				'-g',			#enable debug symbols
				'-O0',			#disable optimizations
			])
		elif build_type == 'Release':
			cxxflags.extend([
				'-O3',			#optimize speed
				'-DNDEBUG',
			])
		elif build_type == 'RelWithDebInfo':
			cxxflags.extend([
				'-g',
				'-O2',
				'-DNDEBUG',
			])
		elif build_type == 'MinSizeRel':
			cxxflags.extend([
				'-Os',			#optimize size
				'-DNDEBUG',
			])

	env.append_value('CXXFLAGS', cxxflags)
	env.append_value('LINKFLAGS', linkflags)

def _apply_os(conf, env):
	#try to map dest os to `waflib.Utils.unversioned_sys_platform()` outputs
	#first, then fallback to just using the conan name directly
	settings = env.CONAN_SETTINGS
	
	os = settings.get('os', None)
	if os == None:
		return

	if os == 'Macos':
		os = 'darwin'
	elif os == 'Windows':
		os = 'win32'
	else:
		os = os.lower()
	env['DEST_OS'] = os

	version = settings.get('os.version')
	if version:
		env['DEST_OS_VERSION'] = version

	if os == 'win32' and settings.get('os.subsystem'):
		env['WINDOWS_SUBSYSTEM'] = settings['os.subsystem']

	if os == 'android':
		env['ANDROID_MINSDKVERSION'] = settings.get('os.api_level')

	if os in ['ios', 'tvos', 'watchos']:
		env['IOS_SDK_NAME'] = settings['os.sdk']
		env['IOS_SDK_MINVER'] = settings.get('os.sdk_version')

def _apply_arch(conf, env):
	arch = env.CONAN_SETTINGS.get('arch', None)
	if arch == None:
		return

	#based on Conan settings.yml + `walib.Tools.c_config.MACRO_TO_DEST_CPU`
	#note the original conan arch can be found in the 'CONAN_SETTINGS' key
	archmap = {
		'x86_64': [
			'x86_64'
		],
		'x86': [
			'x86'
		],
		'mips': [
			'mips',
			'mips64'
		],
		'sparc': [
			'sparc',
			'sparcv9',
		],
		'arm':	[
			'armv4',
			'armv4i',
			'armv5el',
			'armv5hf',
			'armv6',
			'armv7',
			'armv7hf',
			'armv7s',
			'armv7k',
			'armv8',
			'armv8_32',
			'armv8.3',
		],
		'powerpc': [
			'ppc32be',
			'ppc32',
			'ppc64le',
			'ppc64',
		],
		'sh': [
			'sh4le',
		],
		's390': [
			's390',
		],
		's390x': [
			's390x',
		],
		'xtensa': [
			'xtensalx6',
			'xtensalx106',
			'xtensalx7',
		],
		'e2k': [
			'e2k-v2',
			'e2k-v3',
			'e2k-v4',
			'e2k-v5',
			'e2k-v6',
			'e2k-v7',
		],

		#in waf, but not in standard conan settings.yml:
		# '__alpha__'	:'alpha',
		# '__hppa__'	:'hppa',
		# '__convex__'	:'convex',
		# '__m68k__'	:'m68k',

		#in conan, but not in waf
		# avr
		# asm.js
		# wasm
	}
	found = None
	for wafname in archmap:
		if arch in archmap[wafname]:
			found = wafname
			break
	if not found:
		found = arch #fallback to conan name
	env['DEST_CPU'] = found

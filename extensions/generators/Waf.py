"""
This generates data in a format fed into the `conan` waf tool
"""
import os
from conan.internal import check_duplicated_generator
from conans.util.files import save


def serialize_configset(data):
	#Emulate waf's ConfigSet serialization format, since this makes it
	#possible to use conan from waf without using a custom waf tool to
	#parse generator output based on `waflib.ConfigSet.ConfigSet.store`,
	#which is unlikely to change
	buf = []
	keys = list(data.keys())
	keys.sort()

	for k in keys:
		buf.append('%s = %s\n' % (k, ascii(data[k])))

	return ''.join(buf)


class Waf(object):
	def __init__(self, conanfile):
		self.conanfile = conanfile


	def get_use_name(self, ref_name, parent_ref = None):
		"""
			see: https://github.com/conan-io/conan/issues/13611#issuecomment-1496300127

				* <pkg>::<pkg> refers to ALL components in a package
				* <comp> refers to a component in the current package
				* <pkg>::<comp> refers to a component in another package
		"""
		assert(type(ref_name) is str)
		assert(not parent_ref or type(parent_ref) is str)
		if '::' in ref_name:
			sp = ref_name.split('::')
			if sp[0] == sp[1]:
				ref_name = sp[0]
			else:
				assert(len(sp[0])>0) #Conan bug?
				ref_name = '_'.join(sp)
		elif parent_ref:
			ref_name = f'{parent_ref}_{ref_name}'
		return ref_name.replace('-', '_')


	def generate(self):
		check_duplicated_generator(self, self.conanfile)

		#serialized waflib.ConfigSet file, which can be loaded by wscript
		filename = os.path.join(
			self.conanfile.generators_folder,
			"conan_waf_config.py"
		)

		output = self.gen_deps()

		#add settings, which will be interpreted and applied at configuration time
		settings = self.conanfile.settings.serialize()
		output.update({
			"CONAN_SETTINGS": settings,
			#paths that should be added to sys.path (only waf tools currently)
			"DEP_SYS_PATHS": self._get_waftools_paths(),
			#global Conan config/flags
			"CONAN_CONFIG": self._get_conan_config()
		})

		generator_files = {filename: serialize_configset(output)}

		for generator_file, content in generator_files.items():
			save(generator_file, content)


	def gen_usedeps(self):
		"""
			Generate CONAN_USE_<x> vars for all components and packages
		"""
		out = {}

		def resolve_pkg(req, dep):
			usename = self.get_use_name(dep.ref.name, dep.ref.name)
			comp_deps = []
			pkg_deps = []
			if dep.has_components:
				comp_deps = list(reversed(dep.cpp_info.get_sorted_components()))


	def gen_deps(self):
		out = {
			"ALL_CONAN_PACKAGES": [],
			"ALL_CONAN_PACKAGES_BUILD": [],
		}
		depmap_host = {}
		depmap_build = {}

		for req, dep in self.conanfile.dependencies.items():
			# print(dep.ref, f", direct={req.direct}, build={req.build}")
			depmap = depmap_build if req.build else depmap_host

			if dep.cpp_info.has_components:
				comp_depnames = []
				#generate "pkg::comp" for each comp
				comps = dep.cpp_info.get_sorted_components().items()
				for ref_name, cpp_info in comps:
					use_name = self.get_use_name(ref_name, dep.ref.name)
					comp_depnames.append(use_name)
					depmap[use_name] = {
						'build': req.build,
						'cpp_info': cpp_info,
						'usename': use_name,
						'requires': [self.get_use_name(c, dep.ref.name) for c in cpp_info.requires],
						'package': self.get_use_name(dep.ref.name),
					}

				#generate a parent "pkg::pkg"
				use_name = self.get_use_name(dep.ref.name)
				# print(f"\tparent use_name: {use_name}")
				depmap[use_name] = {
					'build': req.build,
					'cpp_info': dep.cpp_info,
					'usename': use_name,
					'requires': comp_depnames,
					'package': self.get_use_name(dep.ref.name)
				}
			else:
				#only generate "pkg"
				# print(f"\t<no_components>")
				use_name = self.get_use_name(dep.ref.name)
				depmap[use_name] = {
					'build': req.build,
					'cpp_info': dep.cpp_info,
					'usename': use_name,
					'requires': [self.get_use_name(c, dep.ref.name) for c in dep.cpp_info.requires],
					'package': use_name
				}


		def toposort_deps(self, depmap, root, i):
			out = []
			def visit(n):
				if n.get('__visited', 0) == i:
					return
				assert n.get('__at', 0) != i, "Cyclic dependencies!\n\tusename: %s\n\trequires: %s" % (n['usename'], n['requires'])
				n['__at'] = i
				for req in n['requires']:
					if req not in depmap:
						continue
					# assert req in depmap, "The following dependency for '%s' wasn't found: '%s'\n\tis the package broken, or am I broken?" % (n['usename'], req)
					visit(depmap[req])
				n['__at'] = 0
				n['__visited'] = i
				out.append(n)
			visit(root)
			return out

		sortit = 0

		#generate host dep info (includes, flags, etc)
		for name, info in depmap_host.items():
			sortit += 1
			sorted_deps = toposort_deps(self, depmap_host, info, sortit)
			info['use'] = list(reversed(sorted_deps))
			self.proc_cpp_info(info, out)

		#collect bindirs
		for name, info in depmap_build.items():
			sortit += 1
			sorted_deps = toposort_deps(self, depmap_build, info, sortit)
			info['use'] = list(reversed(sorted_deps))
			self.proc_cpp_info(info, out)

		return out


	def proc_cpp_info(self, depinfo, out):
		name = depinfo['usename']
		pkg_name = depinfo['package']
		cpp_info = depinfo['cpp_info']

		def setvar(k, v):
			if v:
				out[f"{k}_{name}"] = v

		def setpath(k, v):
			#convert relative paths from conan to absolute
			if type(v) is list:
				ret = [os.path.abspath(p) for p in v]
				setvar(k, ret)
				return ret
			else:
				assert type(v) is str
				ret = [os.path.abspath(v)]
				setvar(k, ret[0])
				return ret

		if depinfo['build']:			
			#add 'build_' prefix to all usenames for build items
			#avoids name conflicts while making build graph available in scripts
			name = f'build_{name}'

			out["ALL_CONAN_PACKAGES_BUILD"].append(name)
			#CONAN_USE is used by waftool to expand deps for usenames

			setvar('CONAN_USE', ['build_%s' % d['usename'] for d in depinfo['use']])

			#process build dependencies
			abs_bindirs = setpath("BINPATH", cpp_info.bindirs)
			if 'CONAN_BUILD_BIN_PATH' not in out:
				out['CONAN_BUILD_BIN_PATH'] = set()
			out['CONAN_BUILD_BIN_PATH'].update(abs_bindirs)
		else:
			#process host dependencies
			out["ALL_CONAN_PACKAGES"].append(name)
			
			#CONAN_USE is used by waftool to expand deps for usenames
			setvar('CONAN_USE', [d['usename'] for d in depinfo['use']])

		libs = cpp_info.libs + cpp_info.system_libs + cpp_info.objects
		
		#warning: default waf C/C++ tasks don't distinguish between exelink and
		#sharedlink; will need to override `run_str`. For reference, see:
		#`waflib.Tools.cxx.cxxshlib`. this could be handled by a waftool if it's
		#ever needed

		linkflags = list(set(cpp_info.sharedlinkflags + cpp_info.exelinkflags))
		setvar("LINKFLAGS", linkflags)
		setvar("LIB", libs)
		setpath("LIBPATH", cpp_info.libdirs)
		setvar("CFLAGS", cpp_info.cflags)
		setvar("CXXFLAGS", cpp_info.cxxflags)
		setvar("INCLUDES", cpp_info.includedirs)
		setvar("DEFINES", cpp_info.defines)
		setvar("FRAMEWORK", cpp_info.frameworks)
		setpath("FRAMEWORKPATH", cpp_info.frameworkdirs)

		#Extra non-waf variables from Conan cpp_info
		setpath("SRCPATH", cpp_info.srcdirs)
		setpath("RESPATH", cpp_info.resdirs)
		setpath("BUILDPATH", cpp_info.builddirs)
		setpath("BINPATH", cpp_info.bindirs)

		#Unused waf variables:
		# "ARCH"
		# "STLIB"
		# "STLIBPATH"
		# "LDFLAGS"
		# "RPATH"
		# "CPPFLAGS"


	def _get_conan_config(self):
		conf_info = self.conanfile.conf
		out = {
			"CFLAGS": conf_info.get('tools.build:cflags', [], check_type=list),
			
			"CXXFLAGS": conf_info.get('tools.build:cxxflags', [], check_type=list),
			
			"DEFINES": conf_info.get('tools.build:defines', [], check_type=list),
			
			"LINKFLAGS":
				conf_info.get('tools.build:exelinkflags', [], check_type=list) +
				conf_info.get('tools.build:sharedlinkflags', [], check_type=list),
		}
		return out


	def _get_waftools_paths(self):
		#enables distributing waf tools inside of conan packages
		#e.g. add a waf tool to the 'flatbuffers' package so that you can use
		#the flatc compiler from wscripts, and not worry about versioning
		out = []
		for require, dependency in self.conanfile.dependencies.items():
			if not require.build:
				continue #only find waf tools from build environment
			envvars = dependency.buildenv_info.vars(self.conanfile, scope="build")
			if "WAF_TOOLS" not in envvars.keys():
				continue

			tools = envvars["WAF_TOOLS"].split(" ")
			for entry in tools:
				if not os.path.exists(entry):
					self.outputs.warn(f"Waf tool entry not found: {entry}")
					continue
				if os.path.isfile(entry):
					out.append(os.sep.join(entry.split(os.sep)[:-1]))
				else:
					out.append(entry)
		return out

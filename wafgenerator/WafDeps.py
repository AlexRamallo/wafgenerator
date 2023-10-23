"""
This generates data in a format fed into the `conan` waf tool

Dependencies in waf are implemented with "use" names. The built-in C++ task
generators accept compiler flags and linker inputs using a special naming
convention for environment variables along with the `use` attribute.

Example:

```py
	bld(
		features = "cxx cxxprogram",
		source = "source/main.cpp",
		use = "openssl"
	)
```

Since "openssl" is in the `use` attribute, the `cxx` (compiler) and
`cxxprogram` (linker) tasks will search the current waf environment (not system
environment) for variables like these:

* LIB_openssl
* CXXFLAGS_openssl
* INCLUDES_openssl
* etc...

The full list is at https://waf.io/book/#_foreign_libraries_and_flags (Table 1)

So this generator's job is simply to generate those environment variables for
all Conan dependencies

Intended use:

```py
def configure(conf):
	conf.env.load("build/conanbuildinfo.py")
```
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


class WafDeps(object):
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
			"conan_dependencies.py"
		)

		deps = self.gen_deps()

		generator_files = {filename: serialize_configset(deps)}

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
		}
		self.depmap = {}

		for req, dep in self.conanfile.dependencies.host.items():
			# print(dep.ref, f", direct={req.direct}, build={req.build}")
			if dep.cpp_info.has_components:
				# print("\t<has components>")
				comp_depnames = []
				#generate "pkg::comp" for each comp
				comps = dep.cpp_info.get_sorted_components().items()
				for ref_name, cpp_info in comps:
					use_name = self.get_use_name(ref_name, dep.ref.name)
					# print(f"\t\tcomp: {ref_name} => use_name: {use_name}")
					comp_depnames.append(use_name)
					self.depmap[use_name] = {
						'cpp_info': cpp_info,
						'usename': use_name,
						'requires': [self.get_use_name(c, dep.ref.name) for c in cpp_info.requires],
						'package': self.get_use_name(dep.ref.name),
					}
					# print("\t\t\trequires: %s" % self.depmap[use_name]['requires'])

				#generate a parent "pkg::pkg"
				use_name = self.get_use_name(dep.ref.name)
				# print(f"\tparent use_name: {use_name}")
				self.depmap[use_name] = {
					'cpp_info': dep.cpp_info,
					'usename': use_name,
					'requires': comp_depnames,
					'package': self.get_use_name(dep.ref.name)
				}
			else:
				#only generate "pkg"
				# print(f"\t<no_components>")
				use_name = self.get_use_name(dep.ref.name)
				self.depmap[use_name] = {
					'cpp_info': dep.cpp_info,
					'usename': use_name,
					'requires': [self.get_use_name(c, dep.ref.name) for c in dep.cpp_info.requires],
					'package': use_name
				}

		def toposort_deps(self, root, i):
			out = []
			def visit(n):
				if n.get('__visited', 0) == i:
					return
				assert n.get('__at', 0) != i, "Cyclic dependencies!\n\tusename: %s\n\trequires: %s" % (n['usename'], n['requires'])
				n['__at'] = i
				for req in n['requires']:
					if req not in self.depmap:
						continue
					# assert req in self.depmap, "The following dependency for '%s' wasn't found: '%s'\n\tis the package broken, or am I broken?" % (n['usename'], req)
					visit(self.depmap[req])
				n['__at'] = 0
				n['__visited'] = i
				out.append(n)
			visit(root)
			return out

		sortit = 0
		for name, info in self.depmap.items():
			sortit += 1
			# print(f"toposort {name}\n\trequires: %s" % info['requires'])
			sorted_deps = toposort_deps(self, info, sortit)
			info['use'] = list(reversed(sorted_deps))
			self.proc_cpp_info(info, out)

		return out

	def proc_cpp_info(self, depinfo, out):
		name = depinfo['usename']
		pkg_name = depinfo['package']
		cpp_info = depinfo['cpp_info']

		out["ALL_CONAN_PACKAGES"].append(name)
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
				assert(type(v) is str)
				ret = [os.path.abspath(v)]
				setvar(k, ret[0])
				return ret
		
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
		
		#conan_load will add this to configuration context's 'PATH' so that
		#the usual `find_program` call will find our binaries
		abs_bindirs = setpath("BINPATH", cpp_info.bindirs)
		if 'CONAN_BINPATH' not in out:
			out['CONAN_BINPATH'] = set()
		out['CONAN_BINPATH'].update(abs_bindirs)

		#Unused waf variables:
		# "ARCH"
		# "STLIB"
		# "STLIBPATH"
		# "LDFLAGS"
		# "RPATH"
		# "CPPFLAGS"

		#CONAN_USE is used by waftool to expand deps for usenames
		setvar('CONAN_USE', [d['usename'] for d in depinfo['use']])
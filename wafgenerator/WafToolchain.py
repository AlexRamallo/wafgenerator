"""
	This just serializes all conan settings and passes them to waf as a
	ConfigSet. It's the responsibility of a waftool on the other side to
	parse them.

	Basically, there's no way to implement Conan's concept of "toolchains" in a
	universal way for waf that doesn't require a custom waf tool, so we
	might as well put all the settings parse logic into that tool so that
	everything can be in one place (esp. since we'll get access to waflib)

	For non-consumer waf packages, it should be easy to patch that tool into any
	existing wscript.
"""
import os
from . import WafDeps
from conans.util.files import save

class WafToolchain(object):
	def __init__(self, conanfile):
		self.conanfile = conanfile

	def generate(self):
		settings = self.conanfile.settings.serialize()

		content = WafDeps.serialize_configset({
			"CONAN_SETTINGS": settings,
			#paths that should be added to sys.path (only waf tools currently)
			"DEP_SYS_PATHS": self._get_waftools_paths(),
			"CONAN_CONFIG": self._get_conan_config(),
		})
		filename = os.path.join(
			self.conanfile.generators_folder, 
			"conan_toolchain.py"
		)
		save(filename, content)

	def _get_conan_config(self):
		conf_info = self.conanfile.conf
		out = {
			"CFLAGS": conf_info.get('tools.build:cflags', [], check_type=list),
			"CXXFLAGS": conf_info.get('tools.build:cxxflags', [], check_type=list),
			"DEFINES": conf_info.get('tools.build:defines', [], check_type=list),
			"LINKFLAGS": conf_info.get('tools.build:exelinkflags', [], check_type=list) + conf_info.get('tools.build:sharedlinkflags', [], check_type=list),
		}
		return out

	def _get_waftools_paths(self):
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
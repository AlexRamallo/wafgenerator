import os, json
from conan import ConanFile
from conan.tools.files import copy

class WafConanTestProject(ConanFile):
    name = "waf_conan_test_sdl"
    version = "1.0"
    settings = "os", "compiler", "build_type", "arch"
    python_requires = "wafgenerator/0.1"
    requires = "spdlog/1.12.0"

    def generate(self):
        WafDeps = self.python_requires["wafgenerator"].module.WafDeps
        WafToolchain = self.python_requires["wafgenerator"].module.WafToolchain

        tc = WafToolchain(self)
        tc.generate()
        
        dep = WafDeps(self)
        dep.generate()
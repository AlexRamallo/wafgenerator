import os
from conan import ConanFile

class WafConanTestProject(ConanFile):
    settings = "os", "compiler", "build_type", "arch"
    requires = "spdlog/1.12.0"

    generators = "Waf"
    # python_requires = "wafgenerator/0.1.5"
    # def generate(self):
    #     gen = self.python_requires["wafgenerator"].module.Waf(self)
    #     gen.generate()


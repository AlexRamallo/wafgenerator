import os, json
from conan import ConanFile
from conan.tools.files import copy

try:
    from extensions.generators.Waf import Waf
except ModuleNotFoundError:
    from Waf import Waf

class WafGenerator(ConanFile):
    name = "wafgenerator"
    version = "0.1.7"
    homepage = "https://github.com/alexramallo/waf-conan-generator"
    description = "A Conan generator for waf"
    license = "MIT"
    package_type = "python-require"
    
    def export(self):
        copy(self, 'extensions/generators/*', self.recipe_folder, self.export_folder, keep_path=False)

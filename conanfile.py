import os, json
from conan import ConanFile
from conan.tools.files import copy

from wafgenerator.WafDeps import WafDeps
from wafgenerator.WafToolchain import WafToolchain

class WafGenerator(ConanFile):
    name = "wafgenerator"
    version = "0.1"
    homepage = "https://github.com/alexramallo/waf-conan-generator"
    description = "A Conan generator for waf"
    license = "MIT"
    package_type = "python-require"
    exports = ["wafgenerator/*"]
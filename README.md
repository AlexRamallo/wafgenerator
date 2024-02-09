# Waf Conan Generator

Makes it possible to use Conan packages in your Waf projects (WIP)

For complete examples, check the [tests/waf](tests/waf) folder.

## Usage overview

The generator will produce a single file called `conan_deps.py` in the output
folder when you call `conan install`. This file should be loaded as a waf tool
during the configure step **before** loading your compiler. Example:

```py
def configure(conf):
	#point tooldir to the output folder of "conan install"
	conf.load('conan_deps', tooldir='build')

	#the environment will be updated to match the conan build environment, so
	#waf's default compiler detection will find any compilers specified in your
	#tool requires (e.g. cross compilers from the Android NDK)
	conf.load('compiler_cxx')

	#find_program will also search bindirs of Conan packages from your
	#tool_requires
	conf.find_program('flatc')
```

The generated waf tool will also populate the waf environment with variables for
foreign libraries, as described in [section 10.3.3](https://aramallo.com/blog/waf-conan/_foreign_libraries_and_flags)
of the waf book. This makes it easy to use dependencies:

```py
def build(bld):
	bld(
		#the 'conan' feature ensures transient dependencies are added
		features = "cxx cxxprogram conan",
		source = "main.cpp",
		use = "spdlog" # <-- a 'requires' from our conanfile
	)
```

## Installation (method 1)

The easiest way to install this is to run:

```sh
conan config install https://github.com/alexramallo/waf-conan-generator

#or, if you cloned this repo locally:
conan config install /path/to/this/repo

#or, use a symlink:
ln -s /path/to/this/repo/extensions/generators/Waf.py ~/.conan2/extensions/generators/Waf.py
```

This will place the generator at `${CONAN_HOME}/extensions/generators/Waf.py`.
Generators installed this way can be used by name in your conanfiles (both .txt
and .py).

For example:

```
[requires]
spdlog/1.12.0

[generators]
Waf
```

or:

```py
def MyPackage(ConanFile):
	generators = ['Waf']
```

## Installation (method 2)

If you want to be able to control the exact version of this generator, you can
put it in your cache and use it as a regular *python_requires* package.

```sh
#clone this repo, then run:
conan export /path/to/this/repo
```

However, this will only work for `conanfile.py`, and not `conanfile.txt`:

```py
class MyPackage(ConanFile):
    python_requires = "wafgenerator/0.1"
    def generate(self):
        gen = self.python_requires["wafgenerator"].module.Waf(self)
        gen.generate()
```

## Installation (method 3)

Thanks to [John Freeman's Redirectory](https://github.com/thejohnfreeman/redirectory)
project, there's a new way to use this. You can either host your own instance of
a redirectory server, or use his graciously provided public instance:

```
conan remote add redirectory https://conan.jfreeman.dev
```

Then just use the `<package>/<version>@github/<github-username>` format to refer
to packages hosted as Github releases instead of Conan Center.

For example:

```py
class MyPackage(ConanFile):
    python_requires = "wafgenerator/0.1.1@github/alexramallo"
    def generate(self):
        gen = self.python_requires["wafgenerator"].module.Waf(self)
        gen.generate()
```
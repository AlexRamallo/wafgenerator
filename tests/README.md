# Instructions

Run these commands inside the `tests` folder:

```sh
# Make sure Conan generator was exported
$ conan export ..

#Make sure waf script is executable
$ chmod +x ./waf

# Enter test folder
$ cd test_basic

# install deps to 'build' folder
$ conan install . --build=missing -of=build

# configure and build the waf project
$ ../waf configure build
```
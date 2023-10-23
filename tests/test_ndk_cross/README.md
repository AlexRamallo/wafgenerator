```sh
conan install . -of=build --build=missing -pr:h=./android_arm64.profile -pr:b=default
source build/conanbuild.sh
../waf configure build
```
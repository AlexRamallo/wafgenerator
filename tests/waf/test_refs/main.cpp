#include <spdlog/spdlog.h>

int main(int argc, char *argv[]){
	spdlog::info("using spdlog package: \"{}\"", CONAN_REF);
	return 0;
}
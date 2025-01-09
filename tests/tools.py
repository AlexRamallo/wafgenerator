import subprocess


def run(cmd, *, error=False):
    print(f'<<RUN: {cmd}>>')
    process = subprocess.run(cmd, text=True, shell=True)
    output = process.stdout
    ret = process.returncode

    if ret != 0 and not error:
        raise Exception("Failed cmd: {}\n{}".format(cmd, output))
    if ret == 0 and error:
        raise Exception(
            "Cmd succeded (failure expected): {}\n{}".format(cmd, output))
    return output


def save(f, content):
    with open(f, "w") as f:
        f.write(content)


def load(f):
    with open(f, "r") as f:
        return f.read()

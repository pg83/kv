import build
import os

build.flags.allow({
    "coverage": {
        "descr": "instrument the binary; `./build -Dcoverage coverage` writes $(B)/coverage.out",
        "default": "",
    },
    "race": {
        "descr": "build kv with the Go race detector; run with `./build -Drace test`",
        "default": "",
    },
})

COVERAGE = bool(build.flags.coverage)
RACE = bool(build.flags.race)


def mkdir(path):
    return [
        "python3",
        "-c",
        f"from pathlib import Path; Path(r'{path}').mkdir(parents=True, exist_ok=True)",
    ]


def touch(path):
    return [
        "python3",
        "-c",
        f"from pathlib import Path; p=Path(r'{path}'); p.parent.mkdir(parents=True, exist_ok=True); p.touch()",
    ]


GO_SOURCES = [
    path for path in build.glob("$(S)/*.go")
    if not path.endswith("_test.go")
]
GO_INPUTS = [*GO_SOURCES, "$(S)/go.mod"]
GO_ENV = {
    "CGO_ENABLED": "1" if RACE else "0",
    "GOFLAGS": "-mod=readonly -buildvcs=false",
    "GOTOOLCHAIN": "local",
    "GOWORK": "off",
}

kv = command(
    name="kv",
    inputs=GO_INPUTS,
    outputs=["$(B)/bin/kv"],
    cmd=[
        "go", "build",
        "-trimpath",
        "-buildvcs=false",
        *(["-race"] if RACE else []),
        *(["-cover", "-covermode=atomic", "-tags=kvcoverage"] if COVERAGE else []),
        "-o", "$(B)/bin/kv",
        ".",
    ],
    cwd="$(S)",
    env=GO_ENV,
    descr="GO",
    color="cyan",
)

tests = []
coverage_dirs = []

for test_path in build.glob("$(S)/tst/test_*.py"):
    test_name = test_path.rsplit("/", 1)[-1][len("test_"):-len(".py")]
    stamp = f"$(B)/tests/{test_name}.stamp"
    env = {
        "KV_TEST_BINARY": kv.outputs[0],
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    prelude = []
    outputs = [stamp]

    if RACE:
        env["GORACE"] = "halt_on_error=1 atexit_sleep_ms=0"

    if COVERAGE:
        coverage_dir = f"$(B)/coverage/{test_name}"
        env["GOCOVERDIR"] = coverage_dir
        prelude = [mkdir(coverage_dir)]
        coverage_dirs.append(coverage_dir)
        outputs.append(coverage_dir)

    tests.append(command(
        name=f"e2e_{test_name}",
        inputs=[test_path, "$(S)/tst/lib.py"],
        outputs=outputs,
        deps=[kv],
        cmd=[
            *prelude,
            ["python3", test_path],
            touch(stamp),
        ],
        cwd="$(S)",
        env=env,
        descr="EE",
        color="green",
    ))

group("install", kv)
group("e2e", *tests)
group("test", *tests)

if COVERAGE:
    coverage = command(
        name="coverage",
        inputs=["$(S)/dev/coverage.py"],
        outputs=["$(B)/coverage.out"],
        deps=tests,
        cmd=[
            "python3", "$(S)/dev/coverage.py",
            "--output", "$(B)/coverage.out",
            *coverage_dirs,
        ],
        cwd="$(S)",
        env=GO_ENV,
        descr="CV",
        color="magenta",
    )

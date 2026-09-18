import build
import zlib

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

chaos_binary = command(
    name="chaos-binary",
    inputs=GO_INPUTS,
    outputs=["$(B)/bin/kv-chaos"],
    cmd=[
        "go", "build",
        "-trimpath",
        "-buildvcs=false",
        "-tags=" + ("kvchaos,kvcoverage" if COVERAGE else "kvchaos"),
        *(["-cover", "-covermode=atomic"] if COVERAGE else []),
        "-o", "$(B)/bin/kv-chaos",
        ".",
    ],
    cwd="$(S)",
    env=GO_ENV,
    descr="GO",
    color="cyan",
)

CHAOS_POINTS = ",".join([
    "close response:11",
    "http call:5",
    "new request:13",
    "read response:7",
])

plain_tests = []
chaos_tests = []
coverage_dirs = []
chaos_coverage_dirs = []

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

    inputs = [test_path, "$(S)/tst/lib.py"]
    plain_tests.append(command(
        name=f"e2e_{test_name}",
        inputs=inputs,
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

    chaos_stamp = f"$(B)/chaos/{test_name}.stamp"
    chaos_env = {
        "KV_CHAOS": CHAOS_POINTS,
        "KV_CHAOS_SEED": str(zlib.crc32(test_name.encode()) % 100000),
        "KV_TEST_BINARY": chaos_binary.outputs[0],
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    chaos_prelude = []
    chaos_outputs = [chaos_stamp]

    if COVERAGE:
        chaos_coverage_dir = f"$(B)/coverage-chaos/{test_name}"
        chaos_env["GOCOVERDIR"] = chaos_coverage_dir
        chaos_prelude = [mkdir(chaos_coverage_dir)]
        chaos_coverage_dirs.append(chaos_coverage_dir)
        chaos_outputs.append(chaos_coverage_dir)

    chaos_tests.append(command(
        name=f"chaos_{test_name}",
        inputs=inputs,
        outputs=chaos_outputs,
        deps=[chaos_binary],
        cmd=[
            *chaos_prelude,
            ["python3", test_path],
            touch(chaos_stamp),
        ],
        cwd="$(S)",
        env=chaos_env,
        descr="KO",
        color="red",
    ))

chaos_points = command(
    name="chaos-points",
    inputs=[*GO_SOURCES, "$(S)/dev/chaos_points.py"],
    outputs=["$(B)/chaos-points.stamp"],
    cmd=[
        ["python3", "$(S)/dev/chaos_points.py"],
        touch("$(B)/chaos-points.stamp"),
    ],
    cwd="$(S)",
    descr="KO",
    color="red",
)

group("install", kv)
group("e2e", *plain_tests)
group("test", *plain_tests)
group("chaos", chaos_points, *chaos_tests)

if COVERAGE:
    chaos_coverage = command(
        name="coverage-chaos",
        inputs=["$(S)/dev/coverage.py"],
        outputs=["$(B)/coverage-chaos.out"],
        deps=chaos_tests,
        cmd=[
            "python3", "$(S)/dev/coverage.py",
            "--output", "$(B)/coverage-chaos.out",
            "--minimum", "0",
            *chaos_coverage_dirs,
        ],
        cwd="$(S)",
        env=GO_ENV,
        descr="CV",
        color="magenta",
    )

    coverage = command(
        name="coverage",
        inputs=["$(S)/dev/coverage.py"],
        outputs=["$(B)/coverage.out"],
        deps=plain_tests,
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

"""Compile the five final firmware purposes against the packaged deployed-XSA BSP."""
from pathlib import Path
import argparse
import json
import os
import shutil
from build import call, tree
from verify import verify, sha, read, output_outside_package
from common import lock, lock_root, save


def build(package, output, xilinx):
    package, output, xilinx = package.resolve(), output.resolve(), xilinx.resolve()
    output = output_outside_package(package, output)
    verify(package)
    if output.exists():
        raise RuntimeError('A fresh firmware output directory is required')
    output.mkdir(parents=True)
    compiler = xilinx / 'Vitis/2022.2/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe'
    if not compiler.is_file():
        raise RuntimeError('AMD 2022.2 ARM compiler not found: ' + str(compiler))
    bsp = package / 'software/bsp/ps7_cortexa9_0'
    env = os.environ.copy()
    env['PATH'] = str(compiler.parent) + os.pathsep + env['PATH']
    result = {'schema': 'fusion150-final-firmware-build/1', 'status': 'running',
              'original_bit_sha256': sha(package / 'release/hardware.bit'),
              'original_XSA_sha256': sha(package / 'release/hardware.xsa'),
              'compiler_sha256': sha(compiler), 'purposes': {}, 'board_actions': False}
    save(output / 'result.json', result)
    for purpose in ['validation', 'benchmark', 'lifecycle', 'stress', 'official']:
        work = output / purpose
        work.mkdir()
        for name in ['har_net_pl.c', 'har_net_pl.h', 'har_net_lifecycle.h']:
            shutil.copyfile(package / 'software/ps' / name, work / name)
        for name in ['har_fixed.c', 'har_fixed.h']:
            shutil.copyfile(package / 'model/FPGA/runtime' / name, work / name)
        shutil.copyfile(package / 'model/FPGA/runtime/generated/har_parameters.h', work / 'har_parameters.h')
        for path in (package / 'software/ps' / purpose).iterdir():
            if path.is_file():
                shutil.copyfile(path, work / path.name)
        demo = 'demo_bench.h' if purpose == 'benchmark' else 'demo_validation.h'
        shutil.copyfile(package / 'hardware/hls/src' / demo, work / 'har_demo.h')
        for path in (package / 'software/link').iterdir():
            shutil.copyfile(path, work / path.name)
        flags = ['-mcpu=cortex-a9', '-mfpu=neon', '-mfloat-abi=hard', '-O2', '-g', '-std=c99',
                 '-Wall', '-Wextra', '-Werror', '-DHAR_TRANSPORT_VECTOR=1']
        if purpose != 'benchmark':
            flags.append('-DHAR_VALIDATION')
        if purpose == 'stress':
            flags.append('-DHAR_STRESS_ROUNDS=24000')
        if purpose == 'official':
            for path in (package / 'tests/official').iterdir():
                shutil.copyfile(path, work / path.name)
        inputs = tree(work)
        save(work / 'precompile-inputs.json', inputs)
        sources = ['har_fixed.c', 'har_net_pl.c', 'main_zynq.c']
        call('compile', [compiler, *flags, '-I' + str(bsp / 'include'), '-c', *sources], work, work, env=env, timeout=300)
        objects = [str(Path(n).with_suffix('.o')) for n in sources]
        if purpose == 'official':
            call('vectors', [compiler, '-mcpu=cortex-a9', '-c', 'official_vectors.S', '-o', 'official_vectors.o'],
                 work, work, env=env, timeout=180)
            objects.append('official_vectors.o')
        call('link', [compiler, *flags, '-specs=Xilinx.spec', '-Wl,-u,_vector_table', '-Wl,-build-id=none',
                     '-Wl,-T,lscript.ld', '-Wl,-Map,application.map', '-L' + str(bsp / 'lib'),
                     '-o', 'application.elf', *objects, '-Wl,--start-group', '-lxil', '-lgcc', '-lc', '-Wl,--end-group'],
             work, work, env=env, timeout=180)
        if not all(sha(work / name) == value for name, value in inputs.items()):
            raise RuntimeError('A compiled source was changed')
        result['purposes'][purpose] = {'status': 'passed', 'elf_sha256': sha(work / 'application.elf'),
                                       'inputs_sha256': inputs,
                                       'not_deployed': True}
        save(output / 'result.json', result)
        print('FINAL_FIRMWARE_BUILD_PASS ' + purpose, flush=True)
    result['status'] = 'passed'
    save(output / 'result.json', result)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--package', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--xilinx', type=Path, required=True)
    args = ap.parse_args()
    args.out = output_outside_package(args.package, args.out)
    output_existed = args.out.exists()
    with lock(lock_root() / 'eda.lock', {'final_firmware': str(args.out)}):
        try:
            build(args.package, args.out, args.xilinx)
        except BaseException as exc:
            result_path = args.out.resolve() / 'result.json'
            if not output_existed and result_path.is_file():
                result = read(result_path)
                if result.get('status') == 'running':
                    result.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
                    save(result_path, result)
            raise

"""Portable, separately recorded RC rebuild. No download and no historical cutoff reuse.

Only the package and explicitly selected AMD installation provide build inputs.
Only final sources from source-map.json are staged; no source ZIP or historical checkout is needed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from verify import verify, resolve, sha, read, output_outside_package

SUPPORT = Path(__file__).resolve().parent / 'pinned'
sys.path.insert(0, str(SUPPORT))
from common import lock, lock_root, save, freeze
from research_timing import reports, timing_summary, coverage
from research_facts import configuration


def tree(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def call(label, argv, cwd, out, markers=(), env=None, timeout=5400):
    """A stage watchdog limits a hung process, not the user's completion goal."""
    record = {'argv': list(map(str, argv)), 'cwd': str(cwd), 'started': time.time(),
              'timeout_seconds': timeout, 'status': 'running',
              'executable_sha256': sha(Path(argv[0]))}
    meta = out / (label + '.call.json')
    save(meta, record)
    proc = None
    try:
        with (out / (label + '.log')).open('xb') as log:
            proc = subprocess.Popen(list(map(str, argv)), cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                    env=env, creationflags=0x08000000 if os.name == 'nt' else 0)
            record['pid'] = proc.pid
            save(meta, record)
            proc.wait(timeout=timeout)
        record['exit_code'] = proc.returncode
        text = (out / (label + '.log')).read_text(encoding='utf-8', errors='replace')
        if proc.returncode or any(m not in text for m in markers):
            raise RuntimeError(f'{label} exit/marker failure; inspect {out}')
        record['status'] = 'passed'
        return text
    except BaseException as exc:
        record.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        if proc is not None and proc.poll() is None:
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
            proc.wait(timeout=30)
        raise
    finally:
        record['finished'] = time.time()
        if (out / (label + '.log')).exists():
            record['log_sha256'] = sha(out / (label + '.log'))
        save(meta, record)


class Build:
    def __init__(self, a):
        self.package, self.out, self.xilinx = a.package.resolve(), a.out.resolve(), a.xilinx.resolve()
        self.candidate = read(self.package / 'candidate.json')
        self.vivado = self.xilinx / 'Vivado/2022.2/bin/vivado.bat'
        self.hls = self.xilinx / 'Vitis_HLS/2022.2/bin/vitis_hls.bat'
        self.vitis = self.xilinx / 'Vitis/2022.2'
        self.cc = self.xilinx / 'Vitis_HLS/2022.2/tps/mingw/8.3.0/win64.o/nt/bin'
        self.gcc = self.vitis / 'gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe'
        self.inputs = self.out / 'inputs'

    def stage(self, name, function):
        out = self.out / name
        out.mkdir(parents=True, exist_ok=False)
        record = {'schema': 'fusion150-portable-rebuild/1', 'stage': name, 'status': 'running',
                  'started': time.time(), 'build_token': uuid.uuid4().hex,
                  'builder_sha256': sha(Path(__file__)), 'original_sources': self.candidate['sources'],
                  'package_manifest_sha256': sha(self.package / 'MANIFEST.json'),
                  'candidate_sha256': sha(self.package / 'candidate.json'),
                  'formal_acceptance': False, 'board_actions': False,
                  'budget': 'Completion goal; per-call watchdogs only; no old cutoff reused'}
        save(out / 'manifest.json', record)
        try:
            function(out, record)
            record['status'] = 'passed'
        except BaseException as exc:
            record.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
            raise
        finally:
            record['finished'] = time.time()
            save(out / 'manifest.json', record)
        print('RELEASE_REBUILD_STAGE_PASS ' + name, flush=True)

    def preflight(self, out, record):
        record['package_verification'] = verify(self.package)
        tools = [self.vivado, self.hls, self.cc / 'gcc.exe', self.cc / 'g++.exe', self.gcc,
                 self.vitis / 'bin/xsct.bat', self.vitis / 'gnuwin/bin/make.exe']
        assert all(x.is_file() for x in tools), tools
        record['tools'] = {str(p): sha(p) for p in tools}
        assert shutil.disk_usage(self.out).free >= 10 * 1024**3
        self.inputs.mkdir(exist_ok=False)
        mapping = read(self.package / 'source-map.json')
        for role, files in mapping.items():
            for destination, source in files.items():
                target = resolve(self.inputs / role, destination)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(resolve(self.package, source), target)
        save(out / 'extracted-source-files.json', {r:tree(self.inputs / r) for r in mapping})
        src = self.inputs / 'kernel'
        freeze(src)
        record['model_freeze'] = {'status':'passed','locked_files':len(read(src/'freeze/model.lock.json')['files']),
                                  'verifier':'unchanged pinned common.freeze'}
        save(out/'model-freeze.json',record['model_freeze'])
        call('vivado-version', [self.vivado, '-version'], out, out, ['Vivado v2022.2'], timeout=120)

    def host(self, out, record):
        root = self.inputs / 'kernel'
        selected = root / 'research/selected/n1-v5'
        src = selected / 'src'
        record['source_sha256'] = tree(src)
        call('host-build', [self.cc/'g++.exe','-std=c++14','-O2','-Wno-unknown-pragmas',
             '-I'+str(src),selected/'host/host_test.cpp',src/'har_net.cpp','-o',out/'host.exe'],out,out,timeout=180)
        call('host-1796', [out/'host.exe'],out,out,['HOST_EQUIV_PASS'],timeout=180)
        call('reference-build', [self.cc/'gcc.exe','-O2','-std=c99','-I'+str(root/'FPGA/runtime'),
             '-I'+str(root/'FPGA/runtime/generated'),'-c',root/'FPGA/runtime/har_fixed.c','-o',out/'frozen.o'],out,out,timeout=120)
        call('probe-build', [self.cc/'g++.exe','-std=c++14','-O2','-Wno-unknown-pragmas','-I'+str(src),
             '-I'+str(root/'FPGA/runtime'),root/'evidence/20261020_skill_v219/fused_probe.cpp',src/'har_net.cpp',
             out/'frozen.o','-o',out/'probe.exe'],out,out,timeout=180)
        call('probe-frozen', [out/'probe.exe'],out,out,['FUSED_PROBE_PASS'],timeout=180)
        assert tree(src) == record['source_sha256']

    def hls_stage(self, out, record):
        src = self.inputs / 'kernel/research/selected/n1-v5/src'
        work = out / 'w'
        work.mkdir()
        names = ['har_net.cpp','har_net.h','har_parameters.h','har_exp_local.h','har_wflat_defs.h',
                 'har_wflat_body.inc','tb_har_net.cpp','demo_bench.h']
        for name in names:
            shutil.copyfile(src / name, work / name)
        inputs = {name: sha(work/name) for name in names}
        save(out/'compiled-source.json', {'build_token':record['build_token'],
             'source_commit':self.candidate['sources']['kernel']['commit'], 'sha256':inputs,
             'hls_executable':str(self.hls),'hls_executable_sha256':sha(self.hls),'clock_ns':6.5,'top':'har_net'})
        tcl = '''if {[catch {
open_project harnet
set_top har_net
add_files har_net.cpp -cflags {-I.}
add_files -tb tb_har_net.cpp -cflags {-I.}
open_solution solution -flow_target vivado
set_part xc7z020clg400-2
create_clock -period 6.5 -name default
csim_design -clean
puts HAR_CSIM_PASS
csynth_design
puts HAR_CSYNTH_PASS
cosim_design -rtl verilog
puts HAR_COSIM_PASS
export_design -format ip_catalog -rtl verilog
puts HAR_IP_EXPORT_PASS
close_project
} err]} {puts stderr "RESEARCH_HLS_FAILED=$err"; exit 1}
puts RESEARCH_HLS_PASS
exit 0
'''
        (work/'run.tcl').write_text(tcl,encoding='utf-8')
        call('hls',[self.hls,'-f','run.tcl'],work,out,
             ['HAR_CSIM_PASS','HAR_CSYNTH_PASS','HAR_COSIM_PASS','HAR_IP_EXPORT_PASS','RESEARCH_HLS_PASS'],timeout=3600)
        assert all(sha(work/n)==h for n,h in inputs.items())
        ip = work/'harnet/solution/impl/ip'
        assert (ip/'component.xml').is_file()
        save(out/'ip-manifest.json', {'build_token':record['build_token'],
             'source_commit':self.candidate['sources']['kernel']['commit'],
             'dependency_sha256':sha(out/'compiled-source.json'),'ip_files':tree(ip)})
        record.update(hls_clock_ns=6.5,part='xc7z020clg400-2',compiled_sources=inputs)

    def soc(self, out, record):
        hls = self.out/'hls'
        hm = read(hls/'ip-manifest.json')
        ip = hls/'w/harnet/solution/impl/ip'
        assert tree(ip)==hm['ip_files']
        record['hls_manifest_sha256'] = sha(hls/'ip-manifest.json')
        record['kernel_commit'] = hm['source_commit']
        project = out/'net'
        templates = self.inputs/'soc/research/v41hbank4soc_v1'
        bd = (templates/'bd.tcl').read_text(encoding='utf-8')
        bd = bd.replace('__PROJECT_DIR__',project.as_posix()).replace('__IP_REPO__',ip.as_posix())
        impl = (templates/'impl.tcl').read_text(encoding='utf-8').replace('__PROJECT_DIR__',project.as_posix())
        impl = impl.replace('launch_runs synth_1 -jobs 4','launch_runs synth_1 -jobs 1')
        impl = impl.replace('launch_runs impl_1 -to_step write_bitstream -jobs 4','launch_runs impl_1 -to_step write_bitstream -jobs 2')
        gate = r'''set errors [get_drc_violations -quiet -filter {SEVERITY == Error}]
if {[llength $errors]} {error "DRC errors: $errors"}
check_timing -verbose -file "$reports/check_timing.rpt"
set cf [open "$reports/check_timing.rpt" r];set cov [read $cf];close $cf
foreach {full category count} [regexp -all -inline {checking ([a-z_]+) \(([0-9]+)\)} $cov] {
 if {$count > 0} {error "Timing coverage failed: $category=$count"}
}
report_methodology -file "$reports/methodology.rpt"
report_timing -delay_type max -max_paths 10 -file "$reports/setup_paths.rpt"
report_timing -delay_type min -max_paths 10 -file "$reports/hold_paths.rpt"
'''
        impl = impl.replace('# ---- 6. bitstream ----',gate+'\n# ---- 6. bitstream ----')
        for name,text in [('bd.tcl',bd),('impl.tcl',impl)]:
            (out/name).write_text('set_param general.maxThreads 4\n'+text,encoding='utf-8')
        record['generated_tcl_sha256']={n:sha(out/n) for n in ['bd.tcl','impl.tcl']}
        save(out/'manifest.json',record)
        call('bd',[self.vivado,'-mode','batch','-source','bd.tcl'],out,out,['NET_SOC_TCL_DONE'])
        bdpath=project/'har_net_soc.srcs/sources_1/bd/har_net_system/har_net_system.bd'
        interfaces=read(bdpath)['design']['components']['har_net_0']['interface_ports']
        record['generated_master_ids']={n:interfaces[n]['parameters']['master_id']['value'] for n in ['m_axi_gmem_in','m_axi_gmem_out']}
        shutil.copyfile(bdpath,out/'generated.bd')
        facts=configuration(project/'ps_config_report.txt',{'xsa_actual_fabric_mhz':150.0,'clocks_ns':{'clk_fpga_0':6.666}})
        save(out/'preimplementation-clock-facts.json',facts)
        assert facts['target_status']=='matches_generated_configuration'
        record['matches_original_master_ids'] = list(map(str,record['generated_master_ids'].values()))==['2','1']
        save(out/'manifest.json',record)
        call('impl',[self.vivado,'-mode','batch','-source','impl.tcl'],out,out,['NET_IMPL_DONE'])
        for name in ['artifacts','impl_reports']:
            shutil.copytree(project/name,out/name)
        shutil.copyfile(out/'impl.log',out/'build_impl.log')
        for name in ['ps_config_report.txt','address_map.txt','acp_topology.txt','acp_elaborated_bd.tcl']:
            shutil.copyfile(project/name,out/name)
        xsa=out/'artifacts/har_net_system.xsa'
        with zipfile.ZipFile(xsa) as z:
            bits=[n for n in z.namelist() if n.endswith('.bit')]
            assert len(bits)==1 and hashlib.sha256(z.read(bits[0])).hexdigest()==sha(out/'artifacts/har_net_system.bit')
            inits=[n for n in z.namelist() if n.endswith('ps7_init.tcl')]
            assert len(inits)==1
            (out/'artifacts/ps7_init.tcl').write_bytes(z.read(inits[0]))
        record['ordinary']=reports(out,{'clk_fpga_0':6.666})
        checkpoint=project/'har_net_soc.runs/impl_1/har_net_system_wrapper_postroute_physopt.dcp'
        assert checkpoint.is_file()
        call('async-review',[self.vivado,'-mode','batch','-source',templates/'review_async.tcl','-tclargs',
             checkpoint,out/'async_reports',templates/'timing-async-2022.tcl'],out,out,['V41_PRESET_CLEAR_REVIEW_PASS'])
        config=(out/'async_reports/timing_config.rpt').read_text()
        assert re.search(r'(?m)^\s*Enable Preset\s*/\s*Clear Arcs\s*:\s*Yes\s*$',config)
        summary=(out/'async_reports/timing_summary_async.rpt').read_text()
        record['expanded']=timing_summary(summary)
        coverage(summary);coverage((out/'async_reports/check_timing.rpt').read_text())
        record['artifacts_sha256']=tree(out/'artifacts')
        record['reports_sha256']=tree(out/'impl_reports')
        record['async_reports_sha256']=tree(out/'async_reports')
        assert tree(ip)==hm['ip_files']

    def arm(self, out, record):
        soc=self.out/'soc';sm=read(soc/'manifest.json');assert sm['status']=='passed'
        root=self.inputs/'firmware';here=root/'research/v40exp4096fw_v1'
        bspwork=out/'bsp-build';bspwork.mkdir()
        xsa=soc/'artifacts/har_net_system.xsa';shutil.copyfile(xsa,bspwork/'hardware.xsa')
        ip=self.out/'hls/w/harnet/solution/impl/ip'
        shutil.copytree(ip/'drivers',bspwork/'repo/drivers')
        shutil.copyfile(root/'research/selected/n1-v5/arm/generate_bsp_2022.tcl',bspwork/'generate.tcl')
        env=os.environ.copy();env['PATH']=str(self.gcc.parent)+';'+str(self.vitis/'gnuwin/bin')+';'+env['PATH'];env['RDI_PLATFORM']='win64'
        call('generate-bsp',[self.vitis/'bin/xsct.bat','generate.tcl',bspwork/'hardware.xsa',bspwork/'bsp',bspwork/'repo'],bspwork,out,['HAR_HSI_BSP_PASS'],env,900)
        call('bsp-make',[self.vitis/'gnuwin/bin/make.exe'],bspwork/'bsp',out,env=env,timeout=600)
        bsp=bspwork/'bsp/ps7_cortexa9_0';inc=bsp/'include'
        xp=(inc/'xparameters.h').read_text()
        def macro(name):
            m=re.search(r'^#define '+name+r'\s+(0x[0-9a-fA-F]+|[0-9]+)',xp,re.M);assert m,name
            return int(m[1],0)
        assert macro('STDOUT_BASEADDRESS')==0xe0001000
        low,high=macro('XPAR_PS7_DDR_0_S_AXI_BASEADDR'),macro('XPAR_PS7_DDR_0_S_AXI_HIGHADDR')
        record['timer_hz']=macro('XPAR_CPU_CORTEXA9_0_CPU_CLK_FREQ_HZ')//2
        record['bsp_sha256']=tree(bspwork/'bsp')
        record['purposes']={}
        for purpose in ['validation','benchmark','lifecycle']:
            work=out/purpose;work.mkdir();token=uuid.uuid4().hex
            ldpath=self.vitis/'data/embeddedsw/lib/sw_apps/openamp_echo_test/src/system/generic/machine/zynq7/lscript.ld'
            ld=ldpath.read_text();ld=re.sub(r'MEMORY\s*\{.*?\}','MEMORY {\n ps7_ddr_0_S_AXI_BASEADDR : ORIGIN = 0x%x, LENGTH = 0x%x\n}'%(low,high-low+1),ld,flags=re.S)
            (work/'lscript.ld').write_text(ld.replace('0x2000;','0x8000;',1))
            spec=self.vitis/'data/embeddedsw/ThirdParty/sw_services/libmetal_v2_4/src/libmetal/test/system/generic/zynq7/Xilinx.spec'
            shutil.copyfile(spec,work/'Xilinx.spec')
            sources=[here/'har_net_pl.c',here/'har_net_pl.h',here/purpose/'main_zynq.c',here/'har_net_lifecycle.h',
                     root/'FPGA/runtime/har_fixed.c',root/'FPGA/runtime/har_fixed.h',root/'FPGA/runtime/generated/har_parameters.h']
            for p in sources:shutil.copyfile(p,work/p.name)
            demo=root/'research/selected/n1-v5/src'/('demo_bench.h' if purpose=='benchmark' else 'demo_validation.h')
            shutil.copyfile(demo,work/'har_demo.h')
            (work/'build_identity.h').write_text('#define HAR_BUILD_TOKEN "'+token+'"\n')
            flags=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-O2','-g','-std=c99','-Wall','-Wextra','-Werror','-DHAR_TRANSPORT_VECTOR=1']
            if purpose!='benchmark':flags+=['-DHAR_VALIDATION']
            inputs={p.name:sha(p) for p in work.iterdir() if p.suffix in ['.c','.h','.ld','.spec']}
            pre={'recorded':time.time(),'purpose':purpose,'token':token,'inputs_sha256':inputs,
                 'bsp_sha256':record['bsp_sha256'],'bit_sha256':sha(soc/'artifacts/har_net_system.bit'),
                 'xsa_sha256':sha(xsa),'soc_manifest_sha256':sha(soc/'manifest.json'),
                 'flags':flags,'linker_template_sha256':sha(ldpath),'spec_template_sha256':sha(spec)}
            save(work/'precompile-inputs.json',pre)
            cfiles=['har_fixed.c','har_net_pl.c','main_zynq.c']
            call('compile',[self.gcc,*flags,'-I'+str(inc),'-c',*cfiles],work,work,env=env,timeout=300)
            call('link',[self.gcc,*flags,'-specs=Xilinx.spec','-Wl,-u,_vector_table','-Wl,-build-id=none',
                 '-Wl,-T,lscript.ld','-Wl,-Map,application.map','-L'+str(bsp/'lib'),'-o','application.elf',
                 *[str(Path(n).with_suffix('.o')) for n in cfiles],'-Wl,--start-group','-lxil','-lgcc','-lc','-Wl,--end-group'],work,work,env=env,timeout=180)
            assert all(sha(work/n)==h for n,h in inputs.items())
            record['purposes'][purpose]={'elf_sha256':sha(work/'application.elf'),'build_token':token,'precompile_inputs_sha256':sha(work/'precompile-inputs.json')}
            save(out/'manifest.json',record)


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--package',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--xilinx',type=Path,required=True)
    ap.add_argument('--stage',choices=['all','preflight','host','hls','soc','arm'],default='all')
    a=ap.parse_args()
    a.out=output_outside_package(a.package,a.out)
    a.out.mkdir(parents=True,exist_ok=True)
    build=Build(a)
    with lock(lock_root()/'eda.lock',{'release_build':str(a.out),'stage':a.stage}):
        for stage,fn in [('preflight',build.preflight),('host',build.host),('hls',build.hls_stage),('soc',build.soc),('arm',build.arm)]:
            if a.stage in ['all',stage]:build.stage(stage,fn)

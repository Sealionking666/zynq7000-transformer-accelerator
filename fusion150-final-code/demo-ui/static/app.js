'use strict';
const $ = id => document.getElementById(id);
let config, selected = '', active = null, offset = 0, lines = [], logKey = '', pending = false;
const datasetNames = {validation:'开发集 · 1796条',official:'官方 test · 2947条',benchmark:'基准固定6个输入'};
function updateDataset(){const official=$('dataset').value==='official';$('validation').textContent=official?'启动官方 test 验证':'启动开发集验证';$('dataset-note').textContent=official?'官方test：2947条 / 17682 logits；PC独立逐值核验。':'开发集：1796条；原固件逐值检查，PC独立汇总核验。';['powered','jtag','exclusive','volatile'].forEach(id=>$(id).checked=false);}
const names = {queued:'排队准备',running:'运行中',completed:'已完成',failed:'失败',stopped:'采集已停止',needs_inspection:'需人工检查'};
function toast(message){ $('notice').textContent = message; $('notice').style.display='block'; clearTimeout(toast.timer); toast.timer=setTimeout(()=>$('notice').style.display='none',9000); }
async function get(path){ const r=await fetch(path,{cache:'no-store'}); const body=await r.json(); if(!r.ok)throw Error(body.error||r.statusText); return body; }
async function post(path,body){ const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Demo-Token':config.token},body:JSON.stringify(body)}); const v=await r.json(); if(!r.ok)throw Error(v.error||r.statusText); return v; }
function link(id, job, file, enabled){const el=$(id); el.classList.toggle('disabled',!enabled); if(enabled)el.href=`/download?job=${job}&file=${encodeURIComponent(file)}`;else el.removeAttribute('href');}
function display(data){
 active=data.active;
 const s=data.selected, jobs=$('jobs'), old=jobs.value;
 const signature=data.jobs.map(j=>j.id+':'+j.status).join('|');
 if(jobs.dataset.signature!==signature){ jobs.replaceChildren(); if(!data.jobs.length){jobs.add(new Option('暂无任务记录',''));} data.jobs.forEach(j=>jobs.add(new Option(`${j.mode==='replay'?'历史回放':'实体板'} · ${datasetNames[j.purpose]||j.purpose} · ${names[j.status]||j.status} · ${j.created.slice(11,19)}`,j.id)));jobs.dataset.signature=signature; }
 if(s){selected=s.id;jobs.value=selected;}
 const busy=!!active||pending;
 ['validation','benchmark','replay','dataset'].forEach(id=>$(id).disabled=busy);
 $('stop').disabled=!active||!['queued','running'].includes(active.status);
 $('connection').textContent = active?.mode==='live'?'当前任务：操作者已确认':'当前连接未确认';
 $('connection').title=data.board;
 if(!s)return;
 const replay=s.mode==='replay', obs=s.observation, review=s.review, good=review?.status==='passed'&&s.status==='completed';
 $('mode-banner').className='mode-banner '+(replay?'':'live');
 $('mode-banner').textContent=replay?`历史日志回放 · ${s.source.record_date} · 不是本次板测`:`本次实体板采集 · ${datasetNames[s.purpose]} · 原 release 工件`;
 $('phase').textContent=s.phase;
 $('task-status').textContent=names[s.status]||s.status;
 $('task-status').className='pill '+(good?'good':['failed','needs_inspection'].includes(s.status)?'bad':'');
 $('source').textContent=replay?`来源：${s.source.path} · SHA256 ${s.source.sha256.slice(0,16)}…`:`数据：${datasetNames[s.purpose]} · 串口 ${s.port} · ${s.purpose} 固件 · 当前连接状态仅由本次工具日志证明`;
 const total=obs?.total, count=obs?.samples;
 $('progress').style.width=(count==null?0:Math.min(100,count/total*100))+'%';
 $('sample-progress').textContent=count==null?'样本数量：尚未取得':s.purpose==='benchmark'?`已记录 ${count}/66 次调用 · 正式计时 ${obs.measured??0}/60 次`:`日志报告 ${count}/${total} 条样本`;
 $('job-time').textContent=s.created.replace('T',' ');
 $('end-line').textContent=obs?.end_line?'已收到（仅终止标记）':'尚未收到';
 $('capture-exit').textContent=replay?'无采集进程（历史）':s.capture_exit_code==null?'尚未退出':`已退出 · code ${s.capture_exit_code}`;
 $('review-status').textContent=review?(review.status==='passed'?review.scope:'核验未通过'):'尚未取得';
 $('numerical').textContent='数值验证：'+(['failed','needs_inspection','stopped'].includes(s.status)?'任务未完成验收；请检查保留记录':(review?.numerical||'尚未取得'));
 $('reason').textContent=s.error||review?.reason||'出现结束行、进程退出与独立核验分开记录。';
 const t=good?obs?.timing:null;
 $('latency-title').textContent=replay?'回放设备 PS/PL 中位延迟':'本次设备 PS/PL 中位延迟';
 $('latency').textContent=t?`${t.pspl_median_us.toFixed(3)} μs`:obs?.timing?'待独立核验':'未提供';
 $('accuracy').textContent=good&&obs?.correct!=null?`${obs.correct}/${obs.samples} · ${(obs.accuracy*100).toFixed(2)}%`:obs?.correct!=null?'日志有汇总，待核验':'未提供';
 $('classification').textContent=good&&obs?.classification?.length?`最近 ${obs.classification.length} 条`:'未提供';
 $('classification-detail').hidden=!obs?.classification?.length;
 $('classification-rows').textContent=obs?.classification?.map(r=>`sample=${r.sample} label=${r.label} prediction=${r.prediction} logits=${r.logits_hex}`).join('\n')||'未提供';
 $('timing-note').textContent=t?`${replay?'历史回放 · ':''}${t.scope}。此中位数来自所选日志，不等同于正式三配对汇总。`:review?.facts?.device_elapsed_seconds_including_uart!=null?`${replay?"历史回放":"本次实体板"}设备整段时间 ${review.facts.device_elapsed_seconds_including_uart.toFixed(4)} 秒，包含逐条校验和UART，不是单次推理延迟。`:(review?.limitation||'该日志尚未提供可独立核验的设备延迟；网页响应、下载和UART不计入推理延迟。');
 const files=s.files||[];
 link('export',s.id,'export.zip',files.includes('export.zip'));
 link('review-file',s.id,'review.json',files.includes('review.json'));
 link('raw-file',s.id,replay?'uart.bin':'capture/uart.bin',files.includes(replay?'uart.bin':'capture/uart.bin'));
 $('run-id').textContent='记录：'+s.id.slice(0,12);
 $('commands').textContent=`任务 ${s.id}\n输出：${s.output}\n开始：${s.created}\n结束：${s.finished||'尚未结束'}\n任务进程退出码：${s.worker_exit?.exit_code??'尚未观测（不是采集退出码）'}\n`+(s.commands||[]).map(c=>`${JSON.stringify(c.argv)}\ncwd=${c.cwd}\n退出码=${c.exit_code??'见任务进程观测记录'}\n`).join('\n');
}
async function readLog(){if(!selected)return;const key=selected+':'+$('stream').value;if(key!==logKey){offset=0;lines=[];logKey=key;$('log').textContent='等待所选日志。';}const d=await get(`/api/log?job=${selected}&stream=${$('stream').value}&offset=${offset}`);if(key!==logKey)return;offset=d.offset;if(d.text){lines.push(d.text);let text=lines.join('');if(text.length>64000)text=text.slice(-64000);const all=text.split('\n');if(all.length>250)text=all.slice(-250).join('\n');lines=[text];$('log').textContent=text;if($('follow').checked)$('log').scrollTop=$('log').scrollHeight;}$('log-count').textContent=`已读 ${offset.toLocaleString()} / ${d.total.toLocaleString()} bytes`;}
async function poll(){try{const d=await get('/api/state'+(selected?'?job='+selected:''));display(d);await readLog();$('service').textContent='本地服务在线 · 页面每秒刷新';}catch(e){$('service').textContent='服务连接中断 · 不代表板卡停止';toast(e.message);}finally{setTimeout(poll,1000);}}
async function start(mode,purpose){if(pending)return;pending=true;['validation','benchmark','replay','dataset'].forEach(id=>$(id).disabled=true);try{const confirmations={powered:$('powered').checked,jtag:$('jtag').checked,exclusive:$('exclusive').checked,volatile:$('volatile').checked};if(mode==='live'&&!Object.values(confirmations).every(Boolean)){ $('confirm-panel').open=true;throw Error('请先逐项核实并勾选本次板卡条件与下载授权');}const d=await post('/api/start',{mode,purpose,history:$('history').value,port:$('port').value.trim().toUpperCase(),xilinx:$('xilinx').value.trim(),confirmations});selected=d.id;logKey='';['powered','jtag','exclusive','volatile'].forEach(id=>$(id).checked=false);toast(mode==='replay'?'正在读取真实历史日志；没有板卡操作':'任务已提交；输出写入代码包外，不会自动重试');}catch(e){toast(e.message);}finally{pending=false;}}
async function init(){try{config=await get('/api/config');$('xilinx').value=config.xilinx_default;$('output-location').textContent='输出：'+config.data;$('identity').textContent=`bit SHA256：${config.artifacts['hardware.bit']}\n与candidate绑定：${config.identity_matches?'一致（完整清单随任务校验）':'不一致，禁止部署'}\nvalidation ELF：${config.artifacts['validation.elf']}\nofficial ELF：${config.artifacts['official.elf']}\nbenchmark ELF：${config.artifacts['benchmark.elf']}`;$('identity').style.whiteSpace='pre-wrap';config.history.forEach(h=>$('history').add(new Option(h.label,h.id)));$('dataset').onchange=updateDataset;updateDataset();$('validation').onclick=()=>start('live',$('dataset').value);$('benchmark').onclick=()=>start('live','benchmark');$('replay').onclick=()=>start('replay');$('stop').onclick=async()=>{try{const d=await post('/api/stop',{id:active?.id});toast(d.message);}catch(e){toast(e.message);}};$('ports').onclick=async()=>{try{const d=await get('/api/ports');$('port-list').replaceChildren();d.ports.forEach(p=>$('port-list').append(new Option(p.description,p.port)));$('port-note').textContent=d.error||`枚举 ${d.ports.length} 个设备；请选择实际串口，未自动连接`; }catch(e){toast(e.message);}};$('jobs').onchange=()=>{selected=$('jobs').value;logKey='';};$('stream').onchange=()=>{logKey='';};poll();}catch(e){$('service').textContent='本地服务未就绪';toast(e.message);}}
init();

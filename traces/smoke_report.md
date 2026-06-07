# iTakt VG Smoke Report

Run ID: `20260607_105239`  
Date: 2026-06-07 10:53:44

| VG | Name | Result | Evidence |
|---|---|---|---|
| VG.4 | `harmful_tool_call_protection` | ✅ PASS | 11 destructive commands all BLOCKED before execution |
| VG.5 | `bash_execution` | ✅ PASS | echo captured: 'Exit code: 0\nstdout:\nsmoke_vg5_sentinel_42' |
| VG.6 | `partial_file_editing` | ✅ PASS | foo()→999 ✓=True  bar()/baz() intact ✓=True  diff=True |
| VG.7 | `deployable_packaging` | ✅ PASS | Dockerfile✓ docker-compose✓ docker_build=PASS |
| VG.8 | `config_env_split` | ✅ PASS | .env.example=✓ gitignored=✓ no_key_in_traces=✓ |
| VG.9 | `yield_not_guess` | ✅ PASS | steps=1 not_maxiter=True answer='2 + 2 equals 4.' |
| VG.3 | `cost_monitoring_hard_cap` | ✅ PASS | cap=500 used=1561 stopped=yes |
| VG.2 | `context_compaction` | ✅ PASS | tokens 1400→339 (76% reduced) trace=compaction_smoke-vg2_20260607_105325.json |
| VG.1 | `parallel_sub_agents` | ✅ PASS | spawns=['coder-1', 'tester-1'] Δt=0.00s<1.5s=True |

**9 passed / 0 failed**

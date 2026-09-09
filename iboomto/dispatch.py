"""Translate workflow inputs without injecting user strings into shell code."""
import os,sys
from .run import main

schedule=os.environ.get('SCHEDULE','')
mode=os.environ.get('INPUT_MODE') or {'0 8 * * *':'daily','0 11 * * 0':'weekly-preview','0 7 4 * *':'monthly'}.get(schedule,'daily')
sys.argv=['iboomto','--mode',mode,'--write']
for env,flag in [('SOURCE','source'),('START','start'),('END','end'),('LANGUAGE','language'),('URL','url'),('PREFIX','prefix'),('QUESTION','question')]:
    value=os.environ.get('INPUT_'+env)
    if value:sys.argv += ['--'+flag,value]
if os.environ.get('INPUT_FORCE','').lower()=='true':sys.argv.append('--force')
main()

"""Orca installer: canonical packages, isolated receipts and integrity before execution."""
import base64
import hashlib
import importlib.util
import io
import os
import shutil
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / 'res' / 'tools' / 'orca.py'
spec = importlib.util.spec_from_file_location('orca_installer', WORKER)
orcasetup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orcasetup)


@pytest.mark.parametrize('plat,arch,method,manifest,name', [
    ('linux','aarch64','deb','latest-linux-arm64.yml','orca-ide_1.4.237_arm64.deb'),
    ('linux','x86_64','deb','latest-linux.yml','orca-ide_1.4.237_amd64.deb'),
    ('darwin','arm64','app','latest-mac.yml','Orca-1.4.237-arm64-mac.zip'),
    ('win32','AMD64','user-setup','latest.yml','orca-windows-setup.exe'),
])
def test_official_package_selection(plat, arch, method, manifest, name):
    # covers: AI-18
    plan = orcasetup.package_plan(plat, arch)
    assert plan['method'] == method
    assert plan['manifest'] == manifest
    assert orcasetup.asset_name(plan, '1.4.237') == name


def test_dry_run_never_contacts_network_or_creates_receipt(tmp_path, monkeypatch):
    # covers: AI-17
    monkeypatch.setattr(orcasetup, 'home_dir', lambda: tmp_path)
    monkeypatch.setattr(orcasetup, 'existing_install', lambda p: False)
    monkeypatch.setattr(orcasetup, 'fetch_manifest', lambda p: pytest.fail('dry run requested network'))
    assert orcasetup.main(['--dry-run']) == 0
    assert not list(tmp_path.iterdir())


def test_existing_install_is_preserved_without_receipt(tmp_path, monkeypatch):
    # covers: AI-14
    monkeypatch.setattr(orcasetup, 'home_dir', lambda: tmp_path)
    monkeypatch.setattr(orcasetup, 'existing_install', lambda p: True)
    monkeypatch.setattr(orcasetup, 'fetch_manifest', lambda p: pytest.fail('existing app requested download'))
    assert orcasetup.main([]) == 0
    assert not list(tmp_path.iterdir())


def test_bad_hash_never_reaches_package_installer(tmp_path, monkeypatch):
    monkeypatch.setattr(orcasetup, 'open_release', lambda url: io.BytesIO(b'corrupt'))
    meta = {'name':'p.deb','size':7,'sha512':base64.b64encode(hashlib.sha512(b'correct').digest()).decode()}
    with pytest.raises(RuntimeError, match='integrity'):
        orcasetup.download('1.4.237', meta, tmp_path)
    assert not list(tmp_path.iterdir())


def test_noninteractive_sudo_does_not_run(tmp_path, monkeypatch):
    # covers: AI-35
    monkeypatch.setattr(orcasetup.sys, 'stdin', io.StringIO())
    monkeypatch.setattr(orcasetup.subprocess, 'run', lambda *a, **k: pytest.fail('sudo executed without terminal'))
    with pytest.raises(RuntimeError, match='terminal'):
        orcasetup.run_command(['sudo','apt','install','-y','--',str(tmp_path/'p.deb')], needs_sudo=True)


def test_uninstall_without_receipt_preserves_existing_install(tmp_path, monkeypatch):
    # covers: AI-34
    monkeypatch.setattr(orcasetup, 'home_dir', lambda: tmp_path)
    monkeypatch.setattr(orcasetup, 'run_command', lambda *a, **k: pytest.fail('unowned installation removed'))
    assert orcasetup.main(['--uninstall']) == 0
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell test")
def test_setup_tools_dry_run_does_not_install_default_hooks(tmp_path):
    # covers: AI-17, AI-18
    import os
    env=dict(os.environ, HOME=str(tmp_path),USERPROFILE=str(tmp_path))
    p=subprocess.run(['bash',str(ROOT/'scripts/setup.sh'),'--tools','orca','--dry-run'],
                     capture_output=True,text=True,env=env,timeout=15)
    assert p.returncode == 0, p.stdout+p.stderr
    assert 'Orca' in p.stdout
    assert not (tmp_path/'.claude').exists()


def test_success_records_package_and_skills_without_changing_other_receipt_keys(tmp_path, monkeypatch):
    # covers: AI-15, AI-37
    manifest=tmp_path/'.claude/.claude-code-setup.json'
    manifest.parent.mkdir();manifest.write_text(json.dumps({'mods':{'user':'preserved'}}))
    cli=tmp_path/'orca-ide';cli.write_text('stub')
    monkeypatch.setattr(orcasetup,'home_dir',lambda:tmp_path)
    monkeypatch.setattr(orcasetup,'existing_install',lambda p:False)
    monkeypatch.setattr(orcasetup,'package_plan',lambda *a:{'method':'app','manifest':'latest-mac.yml'})
    monkeypatch.setattr(orcasetup,'install_paths',lambda p:(tmp_path/'Orca.app',cli))
    monkeypatch.setattr(orcasetup,'fetch_manifest',lambda p:('1.4.237',{}))
    monkeypatch.setattr(orcasetup,'download',lambda v,m,d:d/'verified.zip')
    monkeypatch.setattr(orcasetup,'install_package',lambda *a:None)
    monkeypatch.setattr(orcasetup,'installed_version',lambda p:'1.4.237')
    monkeypatch.setattr(orcasetup,'install_skills',lambda p,h,owned,checkpoint=None: owned['skills_added'].update({'orca-cli':'digest'}))
    assert orcasetup.main([])==0
    receipt=json.loads(manifest.read_text())
    assert receipt['mods']=={'user':'preserved'}
    assert receipt['tool_installs']['orca']=={'method':'app','version':'1.4.237','skills_added':{'orca-cli':'digest'},'skills_state':'done'}


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell test")
def test_hooks_uninstall_preserves_orca_receipt(tmp_path):
    import os
    manifest=tmp_path/'.claude/.claude-code-setup.json'
    manifest.parent.mkdir();manifest.write_text(json.dumps({'tool_installs':{'orca':{'method':'app'}}}))
    env=dict(os.environ,HOME=str(tmp_path),USERPROFILE=str(tmp_path))
    script='source "$1/scripts/lib/setup_common.sh"; uninstall_hooks "$2" "$1/res/hooks/merge_and_diff.py" "$HOME/.claude" "$HOME/.claude/hooks" "$HOME/.claude/settings.json" 0'
    p=subprocess.run(['bash','-c',script,'bash',str(ROOT),sys.executable],capture_output=True,text=True,env=env,timeout=15)
    assert p.returncode==0,p.stdout+p.stderr
    assert json.loads(manifest.read_text())['tool_installs']=={'orca':{'method':'app'}}


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell test")
def test_empty_tools_selection_does_not_fall_back_to_default_install(tmp_path):
    import os
    env=dict(os.environ,HOME=str(tmp_path),USERPROFILE=str(tmp_path))
    p=subprocess.run(['bash',str(ROOT/'scripts/setup.sh'),'--tools=','--dry-run'],capture_output=True,text=True,env=env,timeout=15)
    assert p.returncode != 0
    assert not list(tmp_path.iterdir())


def test_partial_skills_are_recorded_after_failed_install(tmp_path, monkeypatch):
    plan={'method':'app','manifest':'latest-mac.yml'}
    cli=tmp_path/'orca';cli.write_text('stub')
    monkeypatch.setattr(orcasetup,'home_dir',lambda:tmp_path)
    monkeypatch.setattr(orcasetup,'existing_install',lambda p:False)
    monkeypatch.setattr(orcasetup,'package_plan',lambda *a:plan)
    monkeypatch.setattr(orcasetup,'install_paths',lambda p:(tmp_path/'Orca.app',cli))
    monkeypatch.setattr(orcasetup,'fetch_manifest',lambda p:('1.4.237',{}))
    monkeypatch.setattr(orcasetup,'download',lambda v,m,d:d/'verified.zip')
    monkeypatch.setattr(orcasetup,'install_package',lambda *a:None)
    monkeypatch.setattr(orcasetup,'installed_version',lambda p:'1.4.237')
    monkeypatch.setattr(orcasetup,'available_skills',lambda cli:['orca-cli'])
    def command(*a,**k):
        skill=tmp_path/'.agents/skills/orca-cli';skill.mkdir(parents=True);(skill/'SKILL.md').write_text('official')
        raise RuntimeError('skills interrupted')
    monkeypatch.setattr(orcasetup,'run_command',command)
    assert orcasetup.main([])==1
    receipt=json.loads((tmp_path/'.claude/.claude-code-setup.json').read_text())['tool_installs']['orca']
    assert receipt['skills_state']=='pending'
    assert 'orca-cli' in receipt['skills_added']
    monkeypatch.setattr(orcasetup,'existing_install',lambda p:True)
    def complete(*a,**k):
        skill=tmp_path/'.agents/skills/orca-cli';skill.mkdir(parents=True,exist_ok=True);(skill/'SKILL.md').write_text('official')
        (tmp_path/'.agents/.skill-lock.json').write_text(json.dumps({'version':3,'skills':{'orca-cli':{'source':'official'}}}))
    monkeypatch.setattr(orcasetup,'run_command',complete)
    assert orcasetup.main([])==0
    receipt=json.loads((tmp_path/'.claude/.claude-code-setup.json').read_text())['tool_installs']['orca']
    assert receipt['skills_state']=='done'


@pytest.mark.parametrize('flags',[['-Tools','orca','-DryRun'],['--tools','orca','--dry-run']])
def test_powershell_tools_dry_run_is_isolated(tmp_path, flags):
    import os,shutil
    pwsh=shutil.which('pwsh')
    if not pwsh:pytest.skip('PowerShell is unavailable')
    env=dict(os.environ,HOME=str(tmp_path),USERPROFILE=str(tmp_path),LOCALAPPDATA=str(tmp_path/'AppData/Local'))
    p=subprocess.run([pwsh,'-NoProfile','-File',str(ROOT/'scripts/setup.ps1'),*flags],capture_output=True,text=True,env=env,timeout=20)
    assert p.returncode==0,p.stdout+p.stderr
    assert 'Orca' in p.stdout
    assert not (tmp_path/'.claude').exists()


def test_powershell_bootstrap_forwards_tools(tmp_path):
    import os,shutil,zipfile
    pwsh=shutil.which('pwsh')
    if not pwsh:pytest.skip('PowerShell is unavailable')
    archive=tmp_path/'repo.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('repo/scripts/setup.ps1', 'param([string]$Tools,[switch]$DryRun)\nif($Tools -ne "orca" -or -not $DryRun){exit 41}\nWrite-Output "TOOLS_FORWARDED"\nexit 0\n')
    mock="function Invoke-WebRequest { param($Uri,$OutFile,$UseBasicParsing,$Headers) Copy-Item '"+str(archive).replace("'","''")+"' $OutFile }\n"
    text=(ROOT/'install.ps1').read_text(encoding='utf-8').replace('Set-StrictMode -Version Latest','Set-StrictMode -Version Latest\n'+mock)
    script=tmp_path/'install.ps1';script.write_text(text)
    env=dict(os.environ,HOME=str(tmp_path),USERPROFILE=str(tmp_path),TEMP=str(tmp_path),GITHUB_TOKEN='unused')
    p=subprocess.run([pwsh,'-NoProfile','-File',str(script),'-Tools','orca','-DryRun'],capture_output=True,text=True,env=env,timeout=25)
    assert p.returncode==0,p.stdout+p.stderr
    assert 'TOOLS_FORWARDED' in p.stdout


def test_existing_skills_links_and_lock_entries_are_preserved(tmp_path, monkeypatch):
    shared=tmp_path/'.agents/skills';shared.mkdir(parents=True)
    (shared/'orca-cli').mkdir();(shared/'orca-cli/SKILL.md').write_text('user content')
    (shared/'orchestration').symlink_to(tmp_path/'missing')
    lock=tmp_path/'.agents/.skill-lock.json';lock.write_text(json.dumps({'version':3,'skills':{'computer-use':{'source':'user'}}}))
    monkeypatch.setattr(orcasetup,'available_skills',lambda cli:['orca-cli','orchestration','computer-use','orca-jira'])
    monkeypatch.setattr(orcasetup,'install_paths',lambda p:(tmp_path,tmp_path/'cli'))
    calls=[]
    def command(argv,**kw):
        calls.append([str(a) for a in argv])
        (shared/'orca-jira').mkdir();(shared/'orca-jira/SKILL.md').write_text('official')
        data=json.loads(lock.read_text());data['skills']['orca-jira']={'source':'official'};lock.write_text(json.dumps(data))
    monkeypatch.setattr(orcasetup,'run_command',command)
    owned={};orcasetup.install_skills({},tmp_path,owned)
    assert calls==[[str(tmp_path/'cli'),'skills','install','--agent','universal','--skill','orca-jira']]
    assert (shared/'orca-cli/SKILL.md').read_text()=='user content'
    assert (shared/'orchestration').is_symlink()
    assert set(owned['skills_added'])=={'orca-jira'}
    assert json.loads(lock.read_text())['skills']['computer-use']=={'source':'user'}


def test_malformed_skill_lock_blocks_install_without_overwrite(tmp_path, monkeypatch):
    lock=tmp_path/'.agents/.skill-lock.json';lock.parent.mkdir();lock.write_text('{broken')
    monkeypatch.setattr(orcasetup,'run_command',lambda *a,**k:pytest.fail('invalid lock was overwritten'))
    with pytest.raises((RuntimeError,ValueError)):
        orcasetup.install_skills({},tmp_path,{})
    assert lock.read_text()=='{broken'


def test_failed_package_stage_is_not_reported_as_existing_success(tmp_path, monkeypatch):
    plan={'method':'app','manifest':'latest-mac.yml'};root=tmp_path/'Orca.app';cli=root/'cli'
    monkeypatch.setattr(orcasetup,'home_dir',lambda:tmp_path)
    monkeypatch.setattr(orcasetup,'existing_install',lambda p:root.exists())
    monkeypatch.setattr(orcasetup,'package_plan',lambda *a:plan)
    monkeypatch.setattr(orcasetup,'install_paths',lambda p:(root,cli))
    monkeypatch.setattr(orcasetup,'fetch_manifest',lambda p:('1.4.237',{}))
    monkeypatch.setattr(orcasetup,'download',lambda v,m,d:d/'verified.zip')
    def install(*a):root.mkdir();raise RuntimeError('package interrupted')
    monkeypatch.setattr(orcasetup,'install_package',install)
    assert orcasetup.main([])==1
    assert orcasetup.main([])==1


def test_dangling_package_link_is_preserved(tmp_path,monkeypatch):
    root=tmp_path/'Orca.app';root.symlink_to(tmp_path/'disconnected-volume')
    monkeypatch.setattr(orcasetup,'install_paths',lambda p:(root,root/'cli'))
    assert orcasetup.existing_install({'method':'app'}) is True


def test_uninstall_cleans_only_owned_skill_link_and_lock_entry(tmp_path,monkeypatch):
    monkeypatch.setattr(orcasetup,'home_dir',lambda:tmp_path)
    monkeypatch.delenv('XDG_STATE_HOME',raising=False);monkeypatch.delenv('XDG_CONFIG_HOME',raising=False)
    shared=tmp_path/'.agents/skills';shared.mkdir(parents=True)
    skill=shared/'orca-cli';skill.mkdir();(skill/'SKILL.md').write_text('official')
    user=shared/'user-skill';user.mkdir();(user/'SKILL.md').write_text('user')
    link=tmp_path/'.config/agents/skills/orca-cli';link.parent.mkdir(parents=True);link.symlink_to(skill)
    lock=tmp_path/'.agents/.skill-lock.json';entry={'source':'stablyai/orca'}
    lock.write_text(json.dumps({'version':3,'skills':{'orca-cli':entry,'user-skill':{'source':'user'}}}))
    root=tmp_path/'Orca.app';root.mkdir();(root/'app').write_text('package')
    monkeypatch.setattr(orcasetup,'install_paths',lambda p:(root,root/'cli'))
    receipt={'tool_installs':{'orca':{'method':'app','skills_added':{'orca-cli':hashlib.sha256(b'SKILL.mdofficial').hexdigest()},
        'skills_links':{'orca-cli':{'link':str(skill)}},'skills_lock':{'orca-cli':entry},'skills_lock_path':str(lock)}}}
    path=tmp_path/'.claude/.claude-code-setup.json';path.parent.mkdir()
    assert orcasetup.uninstall({'method':'app'},receipt,path,False)==0
    assert not root.exists() and not skill.exists() and not link.is_symlink()
    assert (user/'SKILL.md').read_text()=='user'
    assert json.loads(lock.read_text())['skills']=={'user-skill':{'source':'user'}}


def test_changed_skill_retry_does_not_reinvoke_removed_windows_uninstaller(tmp_path,monkeypatch):
    monkeypatch.setattr(orcasetup,'home_dir',lambda:tmp_path)
    monkeypatch.delenv('XDG_STATE_HOME',raising=False);monkeypatch.delenv('XDG_CONFIG_HOME',raising=False)
    skill=tmp_path/'.agents/skills/orca-cli';skill.mkdir(parents=True);(skill/'SKILL.md').write_text('edited')
    root=tmp_path/'Orca';root.mkdir()
    monkeypatch.setattr(orcasetup,'install_paths',lambda p:(root,root/'cli'))
    calls=[]
    def remove(argv,**kw):calls.append(argv);root.rmdir()
    monkeypatch.setattr(orcasetup,'run_command',remove)
    receipt={'tool_installs':{'orca':{'method':'user-setup','skills_added':{'orca-cli':hashlib.sha256(b'SKILL.mdofficial').hexdigest()}}}}
    path=tmp_path/'.claude/.claude-code-setup.json';path.parent.mkdir()
    assert orcasetup.uninstall({'method':'user-setup'},receipt,path,False)==1
    (skill/'SKILL.md').write_text('official')
    assert orcasetup.uninstall({'method':'user-setup'},receipt,path,False)==0
    assert len(calls)==1


@pytest.mark.parametrize('artifact', ['skill', 'link', 'lock'])
def test_uninstall_keeps_unverified_crash_checkpoint_before_package_removal(tmp_path, monkeypatch, artifact):
    monkeypatch.setattr(orcasetup, 'home_dir', lambda: tmp_path)
    monkeypatch.delenv('XDG_STATE_HOME', raising=False)
    monkeypatch.delenv('XDG_CONFIG_HOME', raising=False)
    root = tmp_path / 'Orca.app'; root.mkdir()
    monkeypatch.setattr(orcasetup, 'install_paths', lambda p: (root, root / 'cli'))
    shared, universal, lock = orcasetup.skill_locations(tmp_path)
    if artifact == 'skill':
        target = shared / 'orca-cli'; target.mkdir(parents=True)
        (target / 'SKILL.md').write_text('unverified')
    elif artifact == 'link':
        universal.mkdir(parents=True)
        (universal / 'orca-cli').symlink_to(shared / 'orca-cli')
    else:
        lock.parent.mkdir(parents=True)
        lock.write_text(json.dumps({'version': 3, 'skills': {'orca-cli': {'source': 'unknown'}}}))
    owned = {'method': 'app', 'skills_state': 'pending', 'skills_attempting': ['orca-cli'], 'skills_added': {}}
    receipt = {'tool_installs': {'orca': owned}}
    path = tmp_path / '.claude/.claude-code-setup.json'
    orcasetup.save_receipt(path, receipt)
    with pytest.raises(RuntimeError, match='Preserving changed'):
        orcasetup.uninstall({'method': 'app'}, receipt, path, False)
    assert root.exists()
    assert json.loads(path.read_text())['tool_installs']['orca'] == owned


def test_uninstall_cleans_recorded_lock_when_partial_skill_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(orcasetup, 'home_dir', lambda: tmp_path)
    monkeypatch.delenv('XDG_STATE_HOME', raising=False)
    monkeypatch.delenv('XDG_CONFIG_HOME', raising=False)
    _, _, lock = orcasetup.skill_locations(tmp_path)
    lock.parent.mkdir(parents=True)
    entry = {'source': 'official'}
    lock.write_text(json.dumps({'version': 3, 'skills': {'orca-cli': entry, 'other': {'source': 'user'}}}))
    owned = {'method': 'app', 'package_removed': True, 'skills_state': 'pending',
             'skills_attempting': ['orca-cli'], 'skills_added': {}, 'skills_lock': {'orca-cli': entry}}
    receipt = {'tool_installs': {'orca': owned}}
    path = tmp_path / '.claude/.claude-code-setup.json'
    assert orcasetup.uninstall({'method': 'app'}, receipt, path, False) == 0
    assert json.loads(lock.read_text())['skills'] == {'other': {'source': 'user'}}

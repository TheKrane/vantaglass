"""Theme-scoped shell configuration transforms; no shell commands or device changes."""
import copy

STYLE = 'vantaglass.style'
CLONES = {'vantaglass.'+name: 'omarchy.'+name for name in ('menu','audio','monitor','network','bluetooth','power','clock')}
OWNED = set(CLONES) | {STYLE}

def entry_id(entry):
    return entry if isinstance(entry,str) else entry.get('id') if isinstance(entry,dict) else None

def renamed(entry, name):
    if isinstance(entry,str): return name
    result=copy.deepcopy(entry); result['id']=name; return result

def activate(config, journal=None, conflicts=()):
    """Replace only present enabled native widgets, retaining their options/order."""
    result=copy.deepcopy(config)
    journal=copy.deepcopy(journal or {'disabled_added':[], 'service_added':[], 'bar_before':{k:v for k,v in config.get('bar',{}).items() if k in ('background','transparent')}})
    disabled=result.setdefault('disabledPlugins',[])
    records=result.setdefault('plugins',[])
    layout=result.setdefault('bar',{}).setdefault('layout',{})
    restores=result.setdefault('cloneSourceRestores',[])
    for clone,source in CLONES.items():
        if clone in disabled or source in conflicts: continue
        present=any(entry_id(e)==clone for rows in layout.values() for e in rows) or any(entry_id(e)==clone for e in records)
        if source in disabled and not present: continue
        replaced=False
        for rows in layout.values():
            for i,entry in enumerate(rows):
                if entry_id(entry)==source: rows[i]=renamed(entry,clone);replaced=True
        for i,entry in enumerate(records):
            if entry_id(entry)==source: records[i]=renamed(entry,clone);replaced=True
        if clone.endswith('.menu') and not present and not replaced:
            records.append({'id':clone});journal['service_added'].append(clone);present=True
        if replaced or present:
            if source not in disabled:
                disabled.append(source)
                if source not in journal['disabled_added']:journal['disabled_added'].append(source)
            if source in journal['disabled_added'] and clone not in restores: restores.append(clone)
    if STYLE not in {entry_id(e) for e in records}:
        records.append({'id':STYLE});journal['service_added'].append(STYLE)
    result['bar']['background']='none'
    return result,journal

def deactivate(config,journal=None,uninstall=False):
    """Remove our overlay while retaining unrelated edits made during its use."""
    result=copy.deepcopy(config);journal=journal or {}
    layout=result.get('bar',{}).get('layout',{})
    native={entry_id(e) for rows in layout.values() for e in rows if entry_id(e) not in OWNED}
    for section,rows in layout.items():
        layout[section]=[renamed(e,CLONES[entry_id(e)]) if entry_id(e) in CLONES else e for e in rows if entry_id(e)!=STYLE and not (entry_id(e) in CLONES and CLONES[entry_id(e)] in native)]
    added=set(journal.get('service_added',[]))
    records=[]
    for e in result.get('plugins',[]):
        name=entry_id(e)
        if name==STYLE or name in added:continue
        records.append(renamed(e,CLONES[name]) if name in CLONES else e)
    if 'plugins' in result:result['plugins']=records
    if 'disabledPlugins' in result:
        remove=set(journal.get('disabled_added',[]))
        if uninstall:remove|=OWNED
        result['disabledPlugins']=[e for e in result['disabledPlugins'] if e not in remove]
    if 'cloneSourceRestores' in result:result['cloneSourceRestores']=[e for e in result['cloneSourceRestores'] if e not in OWNED]
    bar=result.get('bar',{})
    if bar.get('background')=='none' and 'bar_before' in journal:
        for k in ('background','transparent'):
            bar.pop(k,None)
            if k in journal['bar_before']:bar[k]=journal['bar_before'][k]
    return result

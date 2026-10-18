// Manual live-test tool. Paste into the Meet tab DevTools, then call start with
// selectors chosen from the current caption DOM. Does not send/store anything.
// Do not point it at chat, the whole page, or a participant list.
globalThis.meetEXObservationRecorder = (profile) => {
  const observations = [], keys = new WeakMap();
  let sequence = 0, observer, previous = new Map(), stopped = false, root;
  const identity = element => { if (!keys.has(element)) keys.set(element, ++sequence); return keys.get(element); };
  const started = performance.now();
  function scan() {
    if (stopped) return;
    const nextRoot = document.querySelector(profile.root);
    if (nextRoot === document.body || nextRoot === document.documentElement) throw new Error('Caption root must be narrow');
    if (root !== nextRoot) {
      observer?.disconnect(); root = nextRoot;
      observations.push({at_ms:performance.now()-started, op:root?'container_attached':'container_lost', container_id:root?identity(root):null});
      if (root) { observer = new MutationObserver(scan); observer.observe(root,{childList:true,subtree:true,characterData:true}); }
    }
    const next = new Map();
    if (root) for (const block of profile.block === ':scope' ? [root] : root.querySelectorAll(profile.block)) {
      const textNode = profile.text === ':scope' ? block : block.querySelector(profile.text);
      if (!textNode) { observations.push({at_ms:performance.now()-started,op:'selector_missing'}); continue; }
      const value = {node_id:identity(block),container_id:identity(root),speaker:profile.speaker?block.querySelector(profile.speaker)?.textContent||null:null,text:textNode.textContent||''};
      next.set(value.node_id,value);
      if (JSON.stringify(value)!==JSON.stringify(previous.get(value.node_id))) observations.push({at_ms:performance.now()-started,op:previous.has(value.node_id)?'edit':'add',...value});
    }
    for (const [node_id,value] of previous) if (!next.has(node_id)) observations.push({at_ms:performance.now()-started,op:'remove',...value});
    previous = next;
  }
  scan(); const watchdog = setInterval(scan,500);
  return {observations,stop(){stopped=true;observer?.disconnect();clearInterval(watchdog);return observations;}};
};

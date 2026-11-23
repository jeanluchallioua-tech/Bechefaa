"""Shared volume calculation for admin previews and actual order alerts."""
SOUND_POLICY_JS = r'''
function notificationChannel(value){
 const raw=value&&typeof value==='object'?(value.sales_channel||value.source||''):value;
 const text=String(raw||'').toUpperCase().replace(/[\s_-]/g,'');
 if(text.includes('DELIVEROO'))return 'deliveroo';
 if(text.includes('UBEREATS'))return 'ubereats';
 if(text.includes('SITE')||text==='WEB'||text==='WIX')return 'site';
 return 'general';
}
function notificationSoundPolicy(settings,page,source='general'){
 const percent=(value,fallback)=>{if(value===undefined||value===null)return fallback/100;const n=Number(value);return Number.isFinite(n)?Math.max(0,Math.min(100,n))/100:fallback/100;};
 const screen=page==='kitchen'?'kitchen':'pos',channel=notificationChannel(source);
 const specific=channel==='deliveroo'||channel==='ubereats';
 return {enabled:settings[screen+'_enabled']!==false&&(!specific||settings[channel+'_enabled']!==false),
  volume:percent(settings[screen+'_volume'],82)*(specific?percent(settings[channel+'_volume'],100):1),channel};
}
'''

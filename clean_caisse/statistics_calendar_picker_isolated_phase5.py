"""Phase 5 — calendrier visuel isolé pour période personnalisée statistiques.

INACTIF : ce module n'est ni importé ni enregistré dans wsgi_caisse.py.
Il ne modifie aucun calcul, aucune donnée, aucun endpoint et aucun Z.
Objectif : permettre de choisir les dates via le calendrier natif du navigateur
sans avoir à les saisir manuellement.
"""


def register_statistics_calendar_picker_isolated_phase5(app):
    @app.after_request
    def statistics_calendar_picker_phase5(response):
        if response.status_code != 200:
            return response
        if not response.content_type or "text/html" not in response.content_type:
            return response

        from flask import request
        if request.path != "/statistiques":
            return response

        html = response.get_data(as_text=True)
        marker = "</body>"
        if marker not in html or 'id="start"' not in html or 'id="end"' not in html:
            return response

        patch = r'''
<style id="phase5-statistics-calendar-picker-style">
#start,#end{cursor:pointer;min-width:150px;padding-right:38px!important;position:relative}
#start::-webkit-calendar-picker-indicator,#end::-webkit-calendar-picker-indicator{
  cursor:pointer;filter:invert(1);opacity:.95;width:22px;height:22px
}
#start:disabled,#end:disabled{cursor:not-allowed;opacity:.55}
.phase5-date-wrap{position:relative;display:flex;align-items:center}
.phase5-date-wrap input{width:100%}
.phase5-date-btn{position:absolute;right:7px;top:50%;transform:translateY(-50%);width:30px;height:30px;min-height:30px!important;padding:0!important;border:0!important;background:transparent!important;box-shadow:none!important;color:#fff!important;font-size:18px;cursor:pointer;z-index:3}
.phase5-date-btn:disabled{cursor:not-allowed;opacity:.4}
</style>
<script id="phase5-statistics-calendar-picker">
(function(){
  function enhance(id){
    const input=document.getElementById(id); if(!input||input.dataset.phase5Calendar==='1')return;
    input.dataset.phase5Calendar='1';
    const wrap=document.createElement('div'); wrap.className='phase5-date-wrap';
    input.parentNode.insertBefore(wrap,input); wrap.appendChild(input);
    const btn=document.createElement('button');
    btn.type='button'; btn.className='phase5-date-btn'; btn.setAttribute('aria-label','Ouvrir le calendrier'); btn.textContent='📅';
    wrap.appendChild(btn);
    const openPicker=function(){
      if(input.disabled)return;
      try{ if(typeof input.showPicker==='function') input.showPicker(); else input.focus(); }catch(e){ input.focus(); }
    };
    btn.addEventListener('click',openPicker);
    input.addEventListener('click',function(){
      if(input.disabled)return;
      try{ if(typeof input.showPicker==='function') input.showPicker(); }catch(e){}
    });
    const sync=function(){btn.disabled=input.disabled;};
    sync();
    const obs=new MutationObserver(sync); obs.observe(input,{attributes:true,attributeFilter:['disabled']});
  }
  enhance('start'); enhance('end');
})();
</script>
'''
        response.set_data(html.replace(marker, patch + marker, 1))
        response.headers["Content-Length"] = len(response.get_data())
        return response
